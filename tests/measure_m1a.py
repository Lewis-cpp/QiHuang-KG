"""Record M1a real HTTP timings, curl chain and SQL plans; API must run on :8000."""

import json
import platform
import re
import statistics
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx

from test_api import ROOT, BUILD, FORMULA, BITTER, LICORICE, COMPOSITION
from backend import queries, services

BITTER_EVIDENCE = 'evidence:001565e0950196b5c0981002ff8467bea6f7bf4791ac34524358cde9ef321a99'


def plans():
    statements = {}
    real_relational = services.relational

    class Recorder:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, statement, params=None):
            key = (statement, json.dumps(params))
            statements[key] = (statement, params)
            return self.cursor.execute(statement, params)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    @contextmanager
    def record(build_id=None):
        with real_relational(build_id) as c:
            yield Recorder(c)

    sections = ['# M1a 查询执行计划', '', '日期：2026-10-10。批次：`' + BUILD + '`。', '',
                'PostgreSQL 18.6，保持默认规划器设置，未禁用顺序扫描。四张大表不允许 Seq Scan；小表 build/dataset 的顺序扫描正常。', '',
                'S1 为四君子汤，S5 为 Bitter medicinal。证据详情分别取组成证据与 S5 实体证据。', '',
                'S5 不适用组成模板，因此模板 SQL 对 S5 的空结果仅用于计划诊断，API 仍返回 422。另附甘草反查的实际计划。', '']
    count = 0
    for name, entity_id, evidence_id in [('S1', FORMULA, COMPOSITION), ('S5', BITTER, BITTER_EVIDENCE)]:
        statements.clear()
        with patch.object(services, 'relational', record):
            queries.entity_detail(entity_id)
            queries.entity_evidence(entity_id, 20, 0)
            queries.evidence_detail(evidence_id)
            if name == 'S1':
                queries.relation_query('formula_herbs', entity_id, 20, 0)
                queries.relation_query('herb_formulas', LICORICE, 20, 0)
            with services.relational() as c:
                for template in ('formula_herbs', 'herb_formulas'):
                    queries.fetch_paths(c, entity_id, queries.TEMPLATES[template][1], 20, 0)
        for number, (statement, params) in enumerate(statements.values(), 1):
            with real_relational() as c:
                c.execute('EXPLAIN (ANALYZE, BUFFERS) ' + statement, params)
                plan = '\n'.join(row['QUERY PLAN'] for row in c.fetchall())
                rendered = c.mogrify(statement, params).decode()
            assert not re.search(r'(?:Parallel )?Seq Scan on (?:\S+\.)?(entity|edge|evidence|alias)\b', plan), (rendered, plan)
            sections += ['## ' + name + ' 查询 ' + str(number), '', '```sql', rendered, '```', '', '```text', plan, '```', '']
            count += 1
    (ROOT / 'docs/query-plans').mkdir(exist_ok=True)
    (ROOT / 'docs/query-plans/m1a.md').write_text('\n'.join(sections))
    return count


def curl_chain():
    calls = []

    def get(path, params=None):
        command = ['curl', '--fail-with-body', '--silent', '--show-error', '--get',
                   'http://127.0.0.1:8000/api/v1' + path]
        for key, value in (params or {}).items():
            command += ['--data-urlencode', key + '=' + value]
        response = json.loads(subprocess.check_output(command))
        assert response['build_id'] == BUILD
        calls.append(dict(command=command, response=response))
        return response

    entity_id = get('/entities', dict(q='四君子汤', type='formula'))['items'][0]['id']
    get('/entities/' + entity_id)
    relations = get('/relation-queries', dict(template='formula_herbs', entity_id=entity_id))
    edge = relations['edges'][relations['paths'][0]['edge_ids'][0]]
    evidence = get('/evidence/' + edge['evidence_ids'][0])
    assert evidence['raw_value']['role'] == 'jun' and evidence['raw_value']['dosage'] == '9g'
    (ROOT / 'docs/acceptance/m1a-chain.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2) + '\n')


def timings():
    cases = [('detail S1', '/entities/' + FORMULA, {}), ('detail S5', '/entities/' + BITTER, {}),
             ('evidence page S1', '/entities/' + FORMULA + '/evidence', {}),
             ('evidence page S5', '/entities/' + BITTER + '/evidence', {}),
             ('evidence detail S1', '/evidence/' + COMPOSITION, {}),
             ('evidence detail S5', '/evidence/' + BITTER_EVIDENCE, {}),
             ('formula_herbs S1', '/relation-queries', dict(template='formula_herbs', entity_id=FORMULA)),
             ('herb_formulas S4', '/relation-queries', dict(template='herb_formulas', entity_id=LICORICE))]
    results = []
    with httpx.Client(base_url='http://127.0.0.1:8000/api/v1', timeout=10) as client:
        for name, path, params in cases:
            for _ in range(5):
                response = client.get(path, params=params)
                assert response.status_code == 200
            durations, sizes, failures = [], [], []
            for _ in range(50):
                started = time.perf_counter()
                try:
                    response = client.get(path, params=params)
                    if response.status_code != 200: failures.append(response.status_code)
                    else: assert response.json()['build_id'] == BUILD
                    sizes.append(len(response.content))
                except httpx.HTTPError as error:
                    failures.append(type(error).__name__)
                durations.append((time.perf_counter() - started) * 1000)
            p95 = sorted(durations)[47]
            results.append(dict(case=name, samples=50, warmup=5, p50_ms=round(statistics.median(durations), 3),
                                p95_ms=round(p95, 3), max_ms=round(max(durations), 3), failures=failures,
                                response_bytes_min=min(sizes), response_bytes_max=max(sizes),
                                analysis='无超过 500 ms 的 P95' if p95 <= 500 else '需复查连接耗时与执行计划'))
    cpu = next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
               if line.startswith('model name'))
    containers = []
    for name in ('postgres', 'neo4j'):
        cid = subprocess.check_output(['docker', 'compose', 'ps', '-q', name], cwd=ROOT).decode().strip()
        value = json.loads(subprocess.check_output(['docker', 'inspect', '--format',
                           '{"memory_bytes": {{.HostConfig.Memory}}, "nano_cpus": {{.HostConfig.NanoCpus}}}', cid]))
        containers.append(dict(service=name, **value))
    report = dict(checked_at=datetime.now(ZoneInfo('Asia/Singapore')).isoformat(), build_id=BUILD,
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                  platform=platform.platform(), cpu=cpu, memory=Path('/proc/meminfo').read_text().splitlines()[0],
                  container_limits=containers, neo4j_heap_mb=512, neo4j_pagecache_mb=256, concurrency=1,
                  transport='real HTTP on loopback with persistent client; API opens one database connection per request',
                  timings=results)
    (ROOT / 'docs/acceptance/m1a-performance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    assert all(not r['failures'] and r['p95_ms'] <= 2000 for r in results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    (ROOT / 'docs/acceptance').mkdir(exist_ok=True)
    count = plans()
    curl_chain()
    timings()
    print('PASS:', count, 'real SQL plans, four curl requests, 8 x 50 real HTTP samples')


if __name__ == '__main__':
    main()
