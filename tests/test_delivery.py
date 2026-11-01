"""Final delivery gate: every acceptance record exists, is self-consistent and matches the frozen evaluation set.

Run with .venv/bin/python tests/test_delivery.py. Contracts: docs/dev/m4b-spec.md §10, m5-spec.md, m6-spec.md, m7-spec.md.
It reads files only (no model, database or browser). The one allowed external block is Vastbase (m6-spec §2).
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACC = ROOT / 'docs/acceptance'
blocked = []


def load(name):
    path = ACC / name
    assert path.is_file(), f'missing acceptance record docs/acceptance/{name}'
    return json.loads(path.read_text(encoding='utf-8'))


def all_ok(name, minimum):
    data = load(name)
    results = data['results'] if 'results' in data else data['steps']
    failed = [r['name'] for r in results if r['ok'] is not True]
    assert len(results) >= minimum and not failed, (name, len(results), failed)
    return data


def m4b():
    data = load('m4-explain.json')
    samples, summary = data['samples'], data['summary']
    assert len(samples) == 10 and data['prompt_version'].startswith('explain_v'), 'ten real explanations'
    assert summary['citations_total'] > 0 and summary['citations_resolved'] == summary['citations_total']
    assert sum(s['citations_resolved'] for s in samples) == summary['citations_resolved']
    assert data['zhu_ling_ze_xie_role_stated'] is False
    assert data['degradation_drill']['status'] == 'explanation_unavailable' and data['degradation_drill']['failure']
    assert (ACC / 'm4-explain-probe.json').is_file()
    browser = all_ok('m4b-browser.json', 5)
    assert any('390' in v for v in browser['viewports'])


def m5():
    frozen = (ROOT / 'eval/test.jsonl.sha256').read_text().split()[0]
    assert hashlib.sha256((ROOT / 'eval/test.jsonl').read_bytes()).hexdigest() == frozen, 'frozen eval set modified'
    report = load('m5-eval-test.json')
    assert report['split'] == 'test' and report['eval_sha256'] == frozen
    expected_ids = [json.loads(line)['id'] for line in (ROOT / 'eval/test.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [s['id'] for s in report['samples']] == expected_ids, 'every frozen sample reported, in order'
    m = report['metrics']
    assert (m['query']['total'], m['explain']['total'], m['adversarial']['total']) == (25, 20, 15)
    assert m['query']['passed'] == sum(s['passed'] for s in report['samples'] if s['category'] == 'query')
    assert m['adversarial']['critical_passed'] == m['adversarial']['critical_total'] == 13, \
        'critical adversarial samples are a hard requirement (m5-spec §8)'
    if m['explain']['citations_total']:
        assert m['explain']['citations_resolved'] == m['explain']['citations_total'], 'citation locatability is 100%'
    for key in ('query', 'explain'):
        if not m[key]['met']:
            assert any(key in gap or ('解释' if key == 'explain' else '查询') in gap for gap in report['gaps']), \
                f'unmet {key} target needs a gap entry'
    assert report['prompt_versions']['query'] and report['prompt_versions']['explain'] and report['model']
    review = load('m5-explain-review.json')
    assert isinstance(review, list) and review and all('supported' in item for item in review)
    assert all(item.get('reviewer') in (None, '') or not str(item['reviewer']).startswith(('agent', 'claude', 'codex'))
               for item in review), 'the agent must not sign the human review'
    all_ok('m5-drills.json', 6)
    browser = all_ok('m5-browser.json', 30)
    for prefix in ('M2-', 'M3-', 'M4-', 'M4B-'):
        assert any(r['name'].startswith(prefix) for r in browser['results']), prefix
    cases = (ROOT / 'tests/cases.md').read_text(encoding='utf-8')
    rows = re.findall(r'^\| (M\d[A-Z]?-\d+) \|', cases, flags=re.M)
    assert len(rows) >= 30 and {r.split('-')[0] for r in rows} >= {'M2', 'M3', 'M4', 'M4B', 'M5'}, sorted(set(rows))


def m6():
    bench = load('m6-bench.json')
    for item in bench['endpoints']:
        assert item['samples'] >= 200 and isinstance(item['failures'], dict), item['name']
        if item['p95_ms'] > item['target_ms']:
            assert any(item['name'] in gap for gap in bench['gaps']), f"{item['name']} misses its target without a gap"
    names = {(e['name'], e['concurrency']) for e in bench['endpoints']}
    assert len(names) >= 24 and {c for _, c in names} == {1, 5}, 'twelve endpoints at concurrency 1 and 5'
    assert (ROOT / 'docs/dev/m6-compat.md').is_file()
    for path in (ROOT / 'backend').glob('*.py'):
        assert '::jsonb' not in path.read_text(encoding='utf-8'), f'{path.name} still uses ::jsonb (m6-spec §1.1)'
    vastbase = load('m6-vastbase.json')
    assert vastbase['status'] in ('passed', 'blocked'), 'failed is not an exit state'
    if vastbase['status'] == 'blocked':
        assert vastbase['reason'] and vastbase.get('next_steps'), 'blocked needs a reason and next steps'
        blocked.append('vastbase')
    else:
        comparison = vastbase['comparison']
        assert all(t['equal'] for t in comparison['tables']) and all(v['equal'] for v in comparison['views'])
        assert vastbase['reader_write_denied'] is True and vastbase['graph_build_match'] is True
        load('m6-bench-vastbase.json')


def m7():
    all_ok('m7-recovery.json', 6)
    for name in ('docs/deploy.md', 'docs/demo-script.md', 'docs/thesis/figures.md', 'docs/acceptance/final-checklist.md'):
        assert (ROOT / name).is_file(), name
    deploy = (ROOT / 'docs/deploy.md').read_text(encoding='utf-8')
    assert 'npm run build' in deploy and 'uvicorn' in deploy and 'check-model' in deploy
    checklist = (ROOT / 'docs/acceptance/final-checklist.md').read_text(encoding='utf-8')
    for requirement in ('Vastbase', 'Neo4j', 'AI', '100,000'):
        assert requirement in checklist, requirement
    if 'vastbase' in blocked:
        assert '阻塞外部' in checklist, 'the checklist must show the Vastbase block'
    issues = (ROOT / 'docs/dev/issues.md').read_text(encoding='utf-8')
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')] for line in issues.splitlines()
            if re.match(r'^\|\s*I-\d+', line)]
    open_blockers = [row[0] for row in rows if len(row) >= 6 and row[2] == '阻断' and row[4] == '未处理']
    assert not open_blockers, open_blockers
    progress = (ROOT / 'docs/dev/progress.md').read_text(encoding='utf-8')
    assert '## 最终总结' in progress


def main():
    m4b()
    m5()
    m6()
    m7()
    print('PASS with BLOCKED: ' + ', '.join(blocked) if blocked else 'PASS: all delivery records complete')


if __name__ == '__main__':
    main()
