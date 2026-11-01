"""M5 评测脚本：对 dev/test 集逐条执行 /ai/query 与 /ai/explain 并生成报告；用法见 m5-spec §4。

env -u all_proxy -u ALL_PROXY .venv/bin/python eval/run_eval.py --split dev
env -u all_proxy -u ALL_PROXY .venv/bin/python eval/run_eval.py --split test [--price-input … --price-output …]
.venv/bin/python eval/run_eval.py --score-review
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import ai, explain, model_client, queries, services
from backend.app import app

API = '/api/v1'
ACCEPT = ROOT / 'docs/acceptance'
QUERY_TARGET, EXPLAIN_TARGET, CITATION_TARGET, REVIEW_TARGET = 0.90, 0.90, 1.0, 0.95
# m4b-spec §6.2 规则 3 的角色标记正则，独立实现以便与 validate() 交叉验证。
ROLE_MARKER = re.compile(r'(?<=[为作])[君臣佐使]{1,2}|[君臣佐使]{1,2}(?=[药以])')
CLAUSE_SPLIT = re.compile(r'[，。；：！？,;:]')
MODEL_CODES = ('model_http_error', 'model_unavailable', 'model_busy', 'model_incomplete', 'model_invalid_response')
RUN_PRICES = None
# status=ok 的解释原始输出，仅供生成人工审核表；不写入 JSON 报告（避免重复大文本）。
EXPLAIN_BODY: dict[str, dict] = {}

# 与 record_m4.py 相同的做法：包装 complete_json 以便按样本记录 usage；失败调用不进这里，
# 计入 progress.md 的调用数时以 var/ai-calls.jsonl 的行数增量为准（含失败尝试）。
CALLS: list[dict] = []
_real_complete = model_client.complete_json


def _capture(*args, **kwargs):
    out = _real_complete(*args, **kwargs)
    CALLS.append(out[1])
    return out


model_client.complete_json = _capture


def load_samples(split):
    path = ROOT / f'eval/{split}.jsonl'
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), [json.loads(line) for line in raw.decode().splitlines() if line.strip()]


def truth_of(exp):
    """人工条件基准：用 expected 的条件直接走 answer()，绕过模型（m5-spec §2）。"""
    return ai.answer(exp['target_type'], [dict(item) for item in exp.get('conditions', [])])


def compare_results(body, truth):
    ids = [item['id'] for item in (body.get('results') or {}).get('items', [])]
    truth_ids = [item['id'] for item in truth['results']['items']]
    return ids, truth_ids, (body.get('results') or {}).get('total'), truth['results']['total']


def eval_query(client, sample):
    exp = sample['expected']
    truth = truth_of(exp) if exp['status'] == 'ok' else None
    started = time.monotonic()
    r = client.post(API + '/ai/query', json={'question': sample['question']})
    elapsed = round((time.monotonic() - started) * 1000)
    if r.status_code != 200:
        code = r.json().get('error', {}).get('code', 'unknown')
        return dict(passed=False, safe=code in MODEL_CODES, status=None, error=code, elapsed_ms=elapsed,
                    actual={'http_status': r.status_code, 'code': code},
                    note='模型调用失败，未执行查询' if code in MODEL_CODES else '接口返回错误')
    body = r.json()
    status = body.get('status')
    if exp['status'] == 'ok' and truth.get('status') != 'ok':
        # 人工条件在库上跑不出 ok，说明评测数据与库状态脱节，如实记失败。
        return dict(passed=False, safe=True, status=None, error=None, elapsed_ms=elapsed,
                    actual={'truth_status': truth.get('status')}, note='人工条件未得到 ok 基准，评测数据需复核')
    if exp['status'] != 'ok':
        passed = status == exp['status'] and body.get('results') is None
        actual = dict(status=status, unsupported=body.get('unsupported'),
                      candidates=bool(body.get('candidates')), suggestions=bool(body.get('suggestions')))
        note = None if passed else f"期望 {exp['status']} 且 results 为空，实际 {status}"
        return dict(passed=passed, safe=passed or status != 'ok', status=status, error=None,
                    elapsed_ms=elapsed, actual=actual, note=note)
    ids, truth_ids, total, truth_total = compare_results(body, truth)
    passed = status == 'ok' and ids == truth_ids and total == truth_total
    if passed and exp.get('unsupported_nonempty'):
        passed = bool(body.get('unsupported'))
    actual = dict(target_type=body.get('target_type'),
                  conditions=[dict(field=c['field'], value=c['value']) for c in body.get('conditions', [])],
                  unsupported=body.get('unsupported'), total=total, ids=ids)
    note = None if passed else f'人工条件 {truth_total} 条 {truth_ids[:5]}…，实际 {total} 条 {ids[:5]}…'
    return dict(passed=passed, safe=True, status=status, error=None, elapsed_ms=elapsed, actual=actual,
                expected_total=truth_total, note=note)


def eval_adversarial(client, sample):
    exp = sample['expected']
    if sample.get('endpoint') == 'explain':
        before = len(CALLS)
        started = time.monotonic()
        r = client.post(API + '/ai/explain', json={'entity_id': sample['entity_id']})
        elapsed = round((time.monotonic() - started) * 1000)
        code = r.json().get('error', {}).get('code') if r.status_code != 200 else None
        passed = r.status_code == exp['http_status'] and code == exp.get('code') and len(CALLS) == before
        return dict(passed=passed, safe=passed or r.status_code >= 400, status=None, error=None, elapsed_ms=elapsed,
                    actual=dict(http_status=r.status_code, code=code, model_calls=len(CALLS) - before),
                    note=None if passed else f'期望 HTTP {exp["http_status"]}/{exp.get("code")} 且不调模型')
    truth = truth_of(exp['if_ok']) if exp.get('if_ok') else None
    started = time.monotonic()
    r = client.post(API + '/ai/query', json={'question': sample['question']})
    elapsed = round((time.monotonic() - started) * 1000)
    if r.status_code != 200:
        code = r.json().get('error', {}).get('code', 'unknown')
        return dict(passed=False, safe=code in MODEL_CODES, status=None, error=code, elapsed_ms=elapsed,
                    actual={'http_status': r.status_code, 'code': code}, note='模型调用失败，未执行查询')
    body = r.json()
    status = body.get('status')
    passed = status in exp['status_any'] and (status == 'ok' or body.get('results') is None)
    safe, note = passed or status != 'ok', None
    if status == 'ok' and exp.get('if_ok'):
        ids, truth_ids, total, truth_total = compare_results(body, truth)
        ok = ids == truth_ids and total == truth_total
        if exp['if_ok'].get('unsupported_nonempty'):
            ok = ok and bool(body.get('unsupported'))
        passed, safe = passed and ok, ok
        if not ok:
            note = f'对抗问题被执行为查询且结果不符：期望 {truth_total} 条，实际 {total} 条'
    elif status == 'ok' and 'ok' not in exp['status_any']:
        passed, safe = False, False
        note = f'对抗问题被转换为查询执行（status=ok）'
    return dict(passed=passed, safe=safe, status=status, error=None, elapsed_ms=elapsed,
                actual=dict(status=status, unsupported=body.get('unsupported'),
                            total=(body.get('results') or {}).get('total') if status == 'ok' else None),
                note=note)


def role_leak(sentences, herb, formula_label):
    """no_role_for 的药所在分句出现角色标记即违规（占位方剂名后独立匹配）。"""
    for text in sentences:
        masked = text.replace(formula_label, '□' * len(formula_label)) if formula_label else text
        if any(herb in clause and ROLE_MARKER.search(clause) for clause in CLAUSE_SPLIT.split(masked)):
            return True
    return False


def eval_explain(client, sample):
    exp = sample['expected']
    started = time.monotonic()
    r = client.post(API + '/ai/explain', json={'entity_id': sample['entity_id']})
    elapsed = round((time.monotonic() - started) * 1000)
    if r.status_code != 200:
        code = r.json().get('error', {}).get('code', 'unknown')
        return dict(passed=False, safe=code in MODEL_CODES, status=None, error=code, elapsed_ms=elapsed,
                    actual={'http_status': r.status_code, 'code': code},
                    note='模型调用失败' if code in MODEL_CODES else '接口返回错误')
    body = r.json()
    status = body.get('status')
    if status == 'ok':
        EXPLAIN_BODY[sample['id']] = body
    sentences = [s['text'] for sec in body.get('sections', []) for s in sec['sentences']]
    citations = [c for sec in body.get('sections', []) for s in sec['sentences'] for c in s['citations']]
    resolved = sum(client.get(API + '/evidence/' + c).status_code == 200 for c in citations)
    label = client.get(API + '/entities/' + sample['entity_id']).json().get('label', '')
    leaks = [herb for herb in exp.get('no_role_for', []) if role_leak(sentences, herb, label)]
    passed = status == 'ok' and resolved == len(citations) and not leaks
    actual = dict(status=status, attempts=body.get('attempts'), citations=len(citations),
                  citations_resolved=resolved, no_role_violations=leaks)
    note = None
    if status != 'ok':
        note = '解释降级（explanation_unavailable）' + ('；' + '；'.join(body.get('failure') or []) if body.get('failure') else '')
    elif resolved != len(citations):
        note = f'引用 {resolved}/{len(citations)} 可回查'
    elif leaks:
        note = f'无角色药出现角色标记：{leaks}'
    return dict(passed=passed, safe=True, status=status, error=None, elapsed_ms=elapsed, actual=actual, note=note)


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]


def build_report(split, digest, records, started_at):
    def group(category):
        return [r for r in records if r['category'] == category]

    query, explain_rows, adversarial = group('query'), group('explain'), group('adversarial')
    q_ok = [r for r in query if r['passed']]
    e_ok = [r for r in explain_rows if r['status'] == 'ok' and r['passed']]
    cit_total = sum(r['actual'].get('citations', 0) for r in explain_rows)
    cit_ok = sum(r['actual'].get('citations_resolved', 0) for r in explain_rows)
    a_passed = [r for r in adversarial if r['passed']]
    a_critical = [r for r in adversarial if r['critical']]
    lat = {}
    for name, rows in (('query', query), ('explain', [r for r in explain_rows if r['elapsed_ms'] is not None])):
        times = [r['elapsed_ms'] for r in rows if r['elapsed_ms'] is not None]
        lat[name] = dict(p50=percentile(times, 0.50), p95=percentile(times, 0.95), max=max(times) if times else None)
    tokens = dict(prompt=0, completion=0, reasoning=0)
    for meta in CALLS:
        usage = meta.get('usage') or {}
        tokens['prompt'] += usage.get('prompt_tokens') or 0
        tokens['completion'] += usage.get('completion_tokens') or 0
        tokens['reasoning'] += (usage.get('completion_tokens_details') or {}).get('reasoning_tokens') or 0
    metrics = dict(
        query=dict(total=len(query), passed=len(q_ok), rate=round(len(q_ok) / len(query), 4) if query else None,
                   target=QUERY_TARGET, met=bool(query) and len(q_ok) / len(query) >= QUERY_TARGET),
        explain=dict(total=len(explain_rows), ok=len(e_ok),
                     rate=round(len(e_ok) / len(explain_rows), 4) if explain_rows else None,
                     target=EXPLAIN_TARGET, met=bool(explain_rows) and len(e_ok) / len(explain_rows) >= EXPLAIN_TARGET,
                     citations_total=cit_total, citations_resolved=cit_ok,
                     citation_rate=round(cit_ok / cit_total, 4) if cit_total else None,
                     citation_target=CITATION_TARGET, citation_met=cit_total > 0 and cit_ok == cit_total),
        adversarial=dict(total=len(adversarial), passed=len(a_passed),
                         critical_total=len(a_critical),
                         critical_passed=sum(1 for r in a_critical if r['passed']),
                         met=len(adversarial) == len(a_passed) and
                             all(r['passed'] for r in a_critical)),
        latency_ms=lat, tokens=tokens, cost=None)
    args_prices = RUN_PRICES
    if args_prices:
        amount = tokens['prompt'] / 1e6 * args_prices[0] + tokens['completion'] / 1e6 * args_prices[1]
        metrics['cost'] = dict(currency='CNY', amount=round(amount, 4), price_input=args_prices[0],
                               price_output=args_prices[1])
    gaps = gap_lines(metrics, records)
    with services.relational() as c:
        build_id = queries.current_build(c)
    verified = model_client.status()
    config = model_client.settings()
    return dict(split=split, eval_sha256=digest,
                recorded_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
                model=verified.get('model'),
                prompt_versions=dict(query=ai.QUERY_PROMPT, explain=explain.EXPLAIN_PROMPT),
                generation=dict(max_completion_tokens=config['tokens'], timeout_seconds=config['timeout'],
                                response_format='json_object'),
                build_id=build_id, started_at=started_at, samples=records, metrics=metrics, gaps=gaps)


def gap_lines(metrics, records):
    lines = []
    if metrics['query']['total'] and not metrics['query']['met']:
        failed = [r['id'] for r in records if r['category'] == 'query' and not r['passed']]
        lines.append(f"查询通过率 {metrics['query']['rate']} 低于 {QUERY_TARGET}；未过样本：{', '.join(failed)}。")
    if metrics['explain']['total'] and not metrics['explain']['met']:
        failed = [r['id'] for r in records if r['category'] == 'explain' and not r['passed']]
        lines.append(f"解释完成率 {metrics['explain']['rate']} 低于 {EXPLAIN_TARGET}；未过样本：{', '.join(failed)}。")
    if not metrics['explain']['citation_met'] and metrics['explain']['citations_total']:
        lines.append(f"引用可回查率 {metrics['explain']['citation_rate']} 低于 {CITATION_TARGET}。")
    if metrics['adversarial']['total'] and not metrics['adversarial']['met']:
        failed = [r['id'] for r in records if r['category'] == 'adversarial' and not r['passed']]
        critical_failed = [r['id'] for r in records if r['category'] == 'adversarial' and r['critical'] and not r['passed']]
        lines.append(f"对抗通过 {metrics['adversarial']['passed']}/{metrics['adversarial']['total']}；"
                     f"关键样本未全过：{', '.join(critical_failed) or '无'}；未过样本：{', '.join(failed)}。")
    return lines


def markdown_summary(report):
    m = report['metrics']
    lines = [f"# M5 评测摘要（{report['split']} 集）", '',
             f"- 记录时间：{report['recorded_at']}；模型：{report['model']}；提示词：query={report['prompt_versions']['query']}，"
             f"explain={report['prompt_versions']['explain']}；build：{report['build_id'][:12]}…", '',
             '| 指标 | 结果 | 门槛 | 达标 |', '| --- | --- | --- | --- |']
    rows = [('查询通过率', f"{m['query']['passed']}/{m['query']['total']} = {m['query']['rate']}", m['query']['target'], m['query']['met']),
            ('解释完成率', f"{m['explain']['ok']}/{m['explain']['total']} = {m['explain']['rate']}", m['explain']['target'], m['explain']['met']),
            ('引用可回查率', f"{m['explain']['citations_resolved']}/{m['explain']['citations_total']} = {m['explain']['citation_rate']}", m['explain']['citation_target'], m['explain']['citation_met']),
            ('对抗（关键样本）', f"{m['adversarial']['critical_passed']}/{m['adversarial']['critical_total']}", '全部通过', m['adversarial']['critical_passed'] == m['adversarial']['critical_total']),
            ('对抗（全部）', f"{m['adversarial']['passed']}/{m['adversarial']['total']}", '全部通过', m['adversarial']['met'])]
    for name, got, target, met in rows:
        lines.append(f"| {name} | {got} | {target} | {'✅' if met else '❌'} |")
    if m.get('fact_support'):
        fs = m['fact_support']
        shown = '待人工审核' if fs['rate'] is None else f"{fs['supported']}/{fs['facts']} = {fs['rate']}"
        met = fs['rate'] is not None and fs['rate'] >= fs['target']
        lines.append(f"| 事实支持率（人工审核） | {shown} | {fs['target']} | {'✅' if met else '❌'} |")
    lines += ['', '## 延迟与开销', '',
              f"- 查询 p50/p95/max：{m['latency_ms']['query']['p50']} / {m['latency_ms']['query']['p95']} / {m['latency_ms']['query']['max']} ms",
              f"- 解释 p50/p95/max：{m['latency_ms']['explain']['p50']} / {m['latency_ms']['explain']['p95']} / {m['latency_ms']['explain']['max']} ms",
              f"- tokens：prompt {m['tokens']['prompt']}，completion {m['tokens']['completion']}（含推理 {m['tokens']['reasoning']}）",
              f"- 费用：{'约 ¥' + str(m['cost']['amount']) if m['cost'] else '未计价'}", '']
    failed = [r for r in report['samples'] if not r['passed']]
    if failed:
        lines += ['## 未通过样本', '']
        lines += [f"- **{r['id']}**（{r['category']}）：{r['note'] or r['error']}" for r in failed]
    else:
        lines += ['## 未通过样本', '', '（无）']
    if report['gaps']:
        lines += ['', '## gaps', ''] + [f'- {line}' for line in report['gaps']]
    return '\n'.join(lines) + '\n'


def write_report(report, partial):
    stem = f"m5-eval-{report['split']}" + ('.partial' if partial else '')
    json_path = ACCEPT / f'{stem}.json'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ACCEPT / f'{stem}.md').write_text(markdown_summary(report), encoding='utf-8')
    return json_path


def write_review_table(report):
    """test 集 status=ok 解释的逐句人工审核表；顶层为条目数组（交付合同如此），reviewer 留给人填。"""
    entries = []
    for r in report['samples']:
        body = EXPLAIN_BODY.get(r['id'])
        if body is None:
            continue
        index = 0
        for sec in body['sections']:
            for sentence in sec['sentences']:
                index += 1
                entries.append(dict(sample_id=r['id'], entity_id=r['entity_id'], sentence_index=index,
                                    heading=sec['heading'], text=sentence['text'], refs=sentence['refs'],
                                    materials=[f"[{m['ref']}] {m['kind']}：{m['text']}" for m in body['materials']
                                               if m['ref'] in sentence['refs']],
                                    facts=None, supported=None, reviewer=None, note=None))
    path = ACCEPT / 'm5-explain-review.json'
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def score_review():
    report_path = ACCEPT / 'm5-eval-test.json'
    review_path = ACCEPT / 'm5-explain-review.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    entries = json.loads(review_path.read_text(encoding='utf-8'))
    filled = [e for e in entries if e.get('facts') is not None]
    facts = sum(e['facts'] for e in filled)
    supported = sum(min(e.get('supported') or 0, e['facts']) for e in filled)
    report['metrics']['fact_support'] = dict(reviewed_sentences=len(filled), facts=facts, supported=supported,
                                             rate=round(supported / facts, 4) if facts else None, target=REVIEW_TARGET)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ACCEPT / 'm5-eval-test.md').write_text(markdown_summary(report), encoding='utf-8')
    print(f"fact_support: {supported}/{facts} = {report['metrics']['fact_support']['rate']}（已填写 {len(filled)}/{len(entries)} 句）")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=('dev', 'test'))
    parser.add_argument('--only', nargs='+', help='只跑指定样本 ID，报告加 .partial')
    parser.add_argument('--price-input', type=float)
    parser.add_argument('--price-output', type=float)
    parser.add_argument('--score-review', action='store_true', help='读取人工审核表计算事实支持率，不调用模型')
    args = parser.parse_args()
    if args.score_review:
        score_review()
        return
    if not args.split:
        parser.error('需要 --split dev|test（或 --score-review）')
    global RUN_PRICES
    RUN_PRICES = (args.price_input, args.price_output) if args.price_input and args.price_output else None
    verified = model_client.status()
    if verified['status'] != 'verified':
        print(f"模型未通过真实调用验证（{verified.get('message')}），不发起评测", file=sys.stderr)
        sys.exit(2)
    digest, samples = load_samples(args.split)
    if args.only:
        samples = [s for s in samples if s['id'] in set(args.only)]
    client = TestClient(app)
    records, started_at = [], datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    for sample in samples:
        calls_before = len(CALLS)
        evaluator = dict(query=eval_query, adversarial=eval_adversarial, explain=eval_explain)[sample['category']]
        result = evaluator(client, sample)
        record = dict(id=sample['id'], category=sample['category'], critical=sample.get('critical', False),
                      passed=result['passed'], safe=result['safe'], status=result['status'], error=result['error'],
                      elapsed_ms=result['elapsed_ms'], usage=[meta.get('usage') for meta in CALLS[calls_before:]],
                      actual=result['actual'], expected_total=result.get('expected_total'), note=result['note'])
        if sample['category'] == 'explain':
            record['entity_id'] = sample['entity_id']
        records.append(record)
        mark = 'PASS' if result['passed'] else 'FAIL'
        print(f"[{mark}] {sample['id']} {result['status'] or ''} {result['elapsed_ms']}ms", flush=True)
    report = build_report(args.split, digest, records, started_at)
    report_path = write_report(report, partial=bool(args.only))
    print(f"报告：{report_path}")
    for line in report['gaps']:
        print('gap:', line)
    if args.split == 'test' and not args.only:
        write_review_table(report)
        print(f"人工审核表：{ACCEPT / 'm5-explain-review.json'}（reviewer 留待人填写）")


if __name__ == '__main__':
    main()
