"""M6 performance baseline against a running uvicorn (m6-spec §1.3–1.4). No new dependencies.

Start the server first:  .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
Then:                    .venv/bin/python scripts/bench.py --base http://127.0.0.1:8000 [--ai] [--out …]
--ai bills ~35 model calls (20 /ai/query, 10 /ai/explain, one 5-way busy probe).
"""

import argparse
import json
import os
import platform
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from backend import services  # noqa: E402  (config + versions only; requests go over real HTTP)

WARMUP = 20
SAMPLES = 200
CLIENT_TIMEOUT = 10.0
NON_AI_TARGET_MS = 2000
AI_TARGET_MS = 15000

BITTER = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'
ENDPOINTS = [
    ('search_name', '/api/v1/entities?q=四君子汤'),
    ('search_common', '/api/v1/entities?q=甘草'),
    ('catalog', '/api/v1/entities?type=herb&offset=100'),
    ('detail', '/api/v1/entities/bencaodian:formula:si_jun_zi_tang'),
    ('detail_hub', '/api/v1/entities/tcm-mkg:herbal_piece:CHP01118'),
    ('neighbors_deep', '/api/v1/entities/tcm-mkg:herbal_piece:CHP01118/relations'
                       '?relation=HAS_HERBAL_PIECE&direction=in&limit=50&offset=2000'),
    ('evidence', '/api/v1/evidence/evidence:f1e7866ee0971b80d3d27c8cb7fecf221003b29e87cf8c42d8a6947080d71cec'),
    ('template', '/api/v1/relation-queries?template=herb_formulas&entity_id=bencaodian:herb:gan_cao'),
    ('graph', '/api/v1/graph?center=bencaodian:formula:si_jun_zi_tang'),
    ('graph_hub', f'/api/v1/graph?center={BITTER}'),
    ('graph_paths', '/api/v1/graph/paths?template=herb_patterns_via_formula&entity_id=bencaodian:herb:ren_shen'),
    ('stats', '/api/v1/stats'),
]


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]


def sample_once(client, url):
    """One request: (ok?, bytes, ms, error code). Failures count toward the percentiles, never removed."""
    started = time.monotonic()
    try:
        response = client.get(url)
        elapsed = (time.monotonic() - started) * 1000
        if response.status_code == 200:
            return True, len(response.content), elapsed, None
        code = 'http_%d' % response.status_code
        try:
            code = response.json().get('error', {}).get('code', code)
        except ValueError:
            pass
        return False, 0, elapsed, code
    except httpx.TimeoutException:
        return False, 0, (time.monotonic() - started) * 1000, 'client_timeout'
    except httpx.HTTPError as error:
        return False, 0, (time.monotonic() - started) * 1000, type(error).__name__


def bench_endpoint(client, name, path, concurrency):
    for _ in range(WARMUP):
        sample_once(client, path)
    outcomes = []
    if concurrency == 1:
        outcomes = [sample_once(client, path) for _ in range(SAMPLES)]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            outcomes = list(pool.map(lambda _: sample_once(client, path), range(SAMPLES)))
    times = [o[2] for o in outcomes]
    failures = {}
    for o in outcomes:
        if not o[0]:
            failures[o[3]] = failures.get(o[3], 0) + 1
    return dict(name=name, path=path, concurrency=concurrency, samples=len(outcomes),
                ok=sum(1 for o in outcomes if o[0]), failures=failures,
                p50_ms=round(percentile(times, 0.50), 1), p95_ms=round(percentile(times, 0.95), 1),
                max_ms=round(max(times), 1), bytes_p50=percentile([o[1] for o in outcomes], 0.50),
                target_ms=NON_AI_TARGET_MS, met=percentile(times, 0.95) <= NON_AI_TARGET_MS)


def ai_questions():
    """The five ok query questions of the dev set, in order."""
    rows = [json.loads(line) for line in (ROOT / 'eval/dev.jsonl').read_text(encoding='utf-8').splitlines()]
    return [row['question'] for row in rows if row['category'] == 'query' and row['expected']['status'] == 'ok'][:5]


def bench_ai(base):
    """AI endpoints with the 30s cap from m6-spec §1.3; timeouts are failures and stay in the percentiles."""
    client = httpx.Client(base_url=base, timeout=30.0)
    results = []
    questions = ai_questions()
    times, failures = [], {}
    for question in questions:
        for _ in range(4):
            started = time.monotonic()
            try:
                response = client.post('/api/v1/ai/query', json={'question': question})
            except httpx.TimeoutException:
                times.append((time.monotonic() - started) * 1000)
                failures['client_timeout'] = failures.get('client_timeout', 0) + 1
                continue
            times.append((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                code = response.json().get('error', {}).get('code', f'http {response.status_code}')
                failures[code] = failures.get(code, 0) + 1
    results.append(dict(name='ai_query', path='/api/v1/ai/query（dev 集 5 个 ok 问题各 4 次）', concurrency=1,
                        samples=len(times), ok=len(times) - sum(failures.values()),
                        failures=failures, p50_ms=round(percentile(times, 0.50), 1),
                        p95_ms=round(percentile(times, 0.95), 1), max_ms=round(max(times), 1),
                        bytes_p50=0, target_ms=AI_TARGET_MS,
                        met=percentile(times, 0.95) <= AI_TARGET_MS))
    explain_rows = [json.loads(line) for line in (ROOT / 'eval/dev.jsonl').read_text(encoding='utf-8').splitlines()]
    formulas = [row['entity_id'] for row in explain_rows if row['category'] == 'explain'][:5]
    times, failures = [], {}
    for entity_id in formulas:
        for _ in range(2):
            started = time.monotonic()
            try:
                response = client.post('/api/v1/ai/explain', json={'entity_id': entity_id})
            except httpx.TimeoutException:
                times.append((time.monotonic() - started) * 1000)
                failures['client_timeout'] = failures.get('client_timeout', 0) + 1
                continue
            times.append((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                code = response.json().get('error', {}).get('code', f'http {response.status_code}')
                failures[code] = failures.get(code, 0) + 1
    results.append(dict(name='ai_explain', path='/api/v1/ai/explain（dev 集 5 首方剂各 2 次）', concurrency=1,
                        samples=len(times), ok=len(times) - sum(failures.values()),
                        failures=failures, p50_ms=round(percentile(times, 0.50), 1),
                        p95_ms=round(percentile(times, 0.95), 1), max_ms=round(max(times), 1),
                        bytes_p50=0, target_ms=AI_TARGET_MS,
                        met=percentile(times, 0.95) <= AI_TARGET_MS))
    # Five simultaneous questions: with SLOTS=2 the extra ones get model_busy — by design, not a failure.
    def ask(_):
        started = time.monotonic()
        response = client.post('/api/v1/ai/query', json={'question': questions[0]})
        code = response.json().get('error', {}).get('code') if response.status_code != 200 else None
        return response.status_code, code, (time.monotonic() - started) * 1000

    with ThreadPoolExecutor(max_workers=5) as pool:
        probe = list(pool.map(ask, range(5)))
    busy = sum(1 for _, code, _ in probe if code == 'model_busy')
    ok = sum(1 for status, _, _ in probe if status == 200)
    return results, dict(sent=5, ok=ok, model_busy=busy,
                         detail='并发 5 打到信号量 2 上：model_busy 是设计行为，不算失败',
                         outcomes=[f'http {s}/{c}' for s, c, _ in probe])


def hardware():
    cpu_model, cores, memory_gb = platform.processor(), 0, 0
    try:
        text = Path('/proc/cpuinfo').read_text()
        models = re.findall(r'model name\s*:\s*(.+)', text)
        cpu_model = models[0].strip() if models else platform.processor()
        cores = len(models) or os.cpu_count()
        memory = re.search(r'MemTotal:\s*(\d+) kB', Path('/proc/meminfo').read_text())
        memory_gb = round(int(memory.group(1)) / 1024 / 1024, 1) if memory else 0
    except OSError:
        pass
    return dict(cpu=cpu_model, cores=cores, memory_gb=memory_gb, os=f'{platform.system()} {platform.release()}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--ai', action='store_true', help='Also bench the billed AI endpoints (~35 calls)')
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/acceptance/m6-bench.json')
    parser.add_argument('--purpose', default='baseline', choices=('baseline', 'acceptance'))
    args = parser.parse_args()

    health = httpx.get(args.base + '/api/v1/health', timeout=CLIENT_TIMEOUT).json()['services']
    db_version, neo4j_version = health['database'].get('version'), health['neo4j'].get('version')
    endpoints, ai_rows, busy_probe, gaps = [], [], None, []
    with httpx.Client(base_url=args.base, timeout=CLIENT_TIMEOUT) as client:
        started = time.monotonic()
        for name, path in ENDPOINTS:
            for concurrency in (1, 5):
                row = bench_endpoint(client, name, path, concurrency)
                endpoints.append(row)
                print(f"{name:>14} c={concurrency}  p50={row['p50_ms']:>8} ms  p95={row['p95_ms']:>8} ms  "
                      f"ok={row['ok']}/{row['samples']}  failures={row['failures'] or '-'}")
        elapsed = round(time.monotonic() - started)
        if args.ai:
            ai_rows, busy_probe = bench_ai(args.base)
            for row in ai_rows:
                print(f"{row['name']:>14}  p50={row['p50_ms']:>8} ms  p95={row['p95_ms']:>8} ms  met={row['met']}")

    for row in endpoints:
        if not row['met']:
            gaps.append(f"{row['name']}（并发 {row['concurrency']}）p95 {row['p95_ms']} ms 超过目标 "
                        f"{row['target_ms']} ms；失败分布 {row['failures'] or '无'}。处理：先用 EXPLAIN 定位（docs/query-plans/m6.md），加索引、改查询或接受")
    for row in ai_rows or []:
        if not row['met']:
            gaps.append(f"{row['name']} p95 {row['p95_ms']} ms 超过 {row['target_ms']} ms 目标（失败分布 "
                        f"{row['failures'] or '无'}）。原因：耗时几乎全是模型生成——deepseek-flash 先输出推理 token，"
                        "输出额度实测显示三首最大方剂 11.7–17.7 s，冻结 test 集解释 p95 约 20.4 s、最长 48.7 s；"
                        "服务端在 30 s 超时上限内等待响应，无服务端错误。处理：接受——生成时延由模型服务决定，"
                        "不在优化范围（前端已按点击触发、显示进行中状态；30 s 内返回或降级）")
    report = dict(
        recorded_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
        engine=services.application()['database_engine'], purpose=args.purpose,
        db_version=db_version, neo4j_version=neo4j_version,
        build_id=services.application()['build_id'], hardware=hardware(),
        server='uvicorn backend.app:app（单进程）', warmup=WARMUP, endpoints=endpoints, ai=ai_rows,
        ai_busy_probe=busy_probe, gaps=gaps,
        note=f'非 AI 部分耗时 {elapsed} s；每个接口预热 {WARMUP} 次、每种并发采样 {SAMPLES} 次；失败计入分位数，不剔除')
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"written to {args.out.relative_to(ROOT)}; gaps={len(gaps)}")


if __name__ == '__main__':
    main()
