"""Record M1b SQL plans and real HTTP timings; API must run on :8000."""

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

from test_api import ROOT, BUILD, CONFLICT, GINSENG, LICORICE, BITTER, ASTRAGALUS, PIECE_LICORICE, PATENT
from backend import queries, services

# Substring search cannot use a B-tree index; spec §4.2 accepts LIKE until P95 exceeds 2 s.
INDEXED = r'(?:Parallel )?Seq Scan on (?:\S+\.)?(edge|evidence)\b'
CASES = [
    ('search exact 甘草', queries.search_entities, ('甘草',), '/entities', dict(q='甘草')),
    ('search single char 草', queries.search_entities, ('草',), '/entities', dict(q='草')),
    ('search alias 黄耆', queries.search_entities, ('黄耆',), '/entities', dict(q='黄耆')),
    ('catalog medicinal_property', queries.search_entities, ('', 'medicinal_property'), '/entities',
     dict(type='medicinal_property')),
    ('relations CONTAINS out S3', queries.entity_relations, (CONFLICT, 'CONTAINS', 'out', 20, 0),
     '/entities/' + CONFLICT + '/relations', dict(relation='CONTAINS', direction='out')),
    ('relations HAS_MEDICINAL_PROPERTY in S5 deep page', queries.entity_relations,
     (BITTER, 'HAS_MEDICINAL_PROPERTY', 'in', 50, 3400), '/entities/' + BITTER + '/relations',
     dict(relation='HAS_MEDICINAL_PROPERTY', direction='in', limit='50', offset='3400')),
    ('formula_patterns S3', queries.relation_query, ('formula_patterns', CONFLICT, 20, 0), '/relation-queries',
     dict(template='formula_patterns', entity_id=CONFLICT)),
    ('herb_patterns_via_formula 甘草', queries.relation_query, ('herb_patterns_via_formula', LICORICE, 20, 0),
     '/relation-queries', dict(template='herb_patterns_via_formula', entity_id=LICORICE)),
    ('patent_medicine_pieces', queries.relation_query, ('patent_medicine_pieces', PATENT, 20, 0),
     '/relation-queries', dict(template='patent_medicine_pieces', entity_id=PATENT)),
    ('piece_patent_medicines 甘草饮片 deep page', queries.relation_query,
     ('piece_patent_medicines', PIECE_LICORICE, 50, 2250), '/relation-queries',
     dict(template='piece_patent_medicines', entity_id=PIECE_LICORICE, limit='50', offset='2250')),
    ('piece_properties 黄芪', queries.relation_query, ('piece_properties', ASTRAGALUS, 20, 0), '/relation-queries',
     dict(template='piece_properties', entity_id=ASTRAGALUS)),
    ('datasets', queries.datasets, (), '/datasets', {}),
]


def plans():
    real_relational = services.relational
    statements = {}

    class Recorder:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, statement, params=None):
            statements.setdefault((statement, json.dumps(params, ensure_ascii=False)), (statement, params))
            return self.cursor.execute(statement, params)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    @contextmanager
    def record(build_id=None):
        with real_relational(build_id) as c:
            yield Recorder(c)

    with real_relational() as c:
        c.execute('SELECT version() AS version')
        version = c.fetchone()['version']
    sections = ['# M1b 查询执行计划', '', '批次：`' + BUILD + '`。服务器：`' + version + '`。', '',
                '保持默认规划器设置。关系与证据查询不允许 edge/evidence 顺序扫描；子串检索按 spec §4.2 '
                '先用 LIKE 实测，entity/alias 顺序扫描是预期结果，耗时见 m1b-performance.json。', '']
    count = 0
    for name, fn, args, _, _ in CASES:
        statements.clear()
        with patch.object(services, 'relational', record):
            fn(*args)
        sections += ['## ' + name, '']
        for statement, params in statements.values():
            if statement.strip() in ('SELECT id FROM build',) or statement.startswith('SELECT * FROM entity WHERE id='):
                continue  # Recorded in m1a.md.
            with real_relational() as c:
                c.execute('EXPLAIN (ANALYZE, BUFFERS) ' + statement, params)
                plan = '\n'.join(row['QUERY PLAN'] for row in c.fetchall())
                rendered = c.mogrify(statement, params).decode()
            if not name.startswith(('search', 'catalog', 'datasets')):
                assert not re.search(INDEXED, plan), (rendered, plan)
            sections += ['```sql', rendered, '```', '', '```text', plan, '```', '']
            count += 1
    (ROOT / 'docs/query-plans/m1b.md').write_text('\n'.join(sections))
    return count, version


def timings(version):
    results = []
    with httpx.Client(base_url='http://127.0.0.1:8000/api/v1', timeout=10) as client:
        for name, _, _, path, params in CASES:
            for _ in range(5):
                assert client.get(path, params=params).status_code == 200
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
                                response_bytes_max=max(sizes)))
    cpu = next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
               if line.startswith('model name'))
    report = dict(checked_at=datetime.now(ZoneInfo('Asia/Singapore')).isoformat(), build_id=BUILD,
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                  database=version, platform=platform.platform(), cpu=cpu, concurrency=1,
                  transport='real HTTP on loopback with persistent client; API opens one database connection per request',
                  timings=results)
    (ROOT / 'docs/acceptance/m1b-performance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    assert all(not r['failures'] and r['p95_ms'] <= 2000 for r in results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    count, version = plans()
    timings(version)
    print('PASS:', count, 'real SQL plans,', len(CASES), 'x 50 real HTTP samples')


if __name__ == '__main__':
    main()
