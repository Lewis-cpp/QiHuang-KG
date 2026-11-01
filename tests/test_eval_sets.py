"""M5 evaluation sets: shape, frozen hash and expectations checked against the database (no model call).

Run with .venv/bin/python tests/test_eval_sets.py. eval/test.jsonl is frozen: never edit it to match results.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import ai, queries, services

EVAL = ROOT / 'eval'
STATUSES = {'ok', 'ambiguous', 'unresolved', 'unsupported'}


def load(name):
    rows = [json.loads(line) for line in (EVAL / f'{name}.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = [row['id'] for row in rows]
    assert len(ids) == len(set(ids)), f'duplicate ids in {name}'
    for row in rows:
        assert row['category'] in ('query', 'explain', 'adversarial'), row
        assert isinstance(row['critical'], bool) and isinstance(row['expected'], dict), row
        assert ('question' in row) != ('entity_id' in row), row
        if 'question' in row:
            assert 1 <= len(row['question']) <= 200, row
    return rows


def frozen():
    data = (EVAL / 'test.jsonl').read_bytes()
    recorded = (EVAL / 'test.jsonl.sha256').read_text().split()[0]
    assert hashlib.sha256(data).hexdigest() == recorded, 'eval/test.jsonl changed after it was frozen'


def counts(dev, test):
    def by(rows):
        return {k: sum(row['category'] == k for row in rows) for k in ('query', 'explain', 'adversarial')}
    assert len(dev) == 20 and by(test) == {'query': 25, 'explain': 20, 'adversarial': 15}, (by(dev), by(test))
    assert not {r.get('question') for r in dev if 'question' in r} & {r.get('question') for r in test if 'question' in r}
    assert not {r['entity_id'] for r in dev if r['category'] == 'explain'} & {r['entity_id'] for r in test if r['category'] == 'explain'}


def as_conditions(items):
    return [dict(field=item['field'], value=item['value'], entity_id=item.get('entity_id')) for item in items]


def query_expectations(rows):
    for row in rows:
        expected = row['expected']
        if 'question' not in row:
            continue
        if 'status' in expected:
            assert expected['status'] in STATUSES, row
        else:
            assert set(expected['status_any']) <= STATUSES, row
        if expected.get('status') == 'ok':
            result = ai.answer(expected['target_type'], as_conditions(expected['conditions']))
            assert result['status'] == 'ok' and result['results']['total'] > 0, (row['id'], result['status'], result['unsupported'])
        elif expected.get('status') in ('ambiguous', 'unresolved'):
            result = ai.answer('formula', as_conditions([expected]))
            assert result['status'] == expected['status'], (row['id'], result['status'])
        if 'if_ok' in expected:
            result = ai.answer(expected['if_ok']['target_type'], as_conditions(expected['if_ok']['conditions']))
            assert result['status'] == 'ok' and result['results']['total'] > 0, row['id']


def explain_expectations(rows):
    with services.relational() as c:
        for row in rows:
            if 'entity_id' not in row:
                continue
            entity = queries.require_entity(c, row['entity_id'])
            if row['category'] == 'adversarial':
                assert entity['type'] != 'formula' and row['expected']['code'] == 'unsupported_entity_type', row
                continue
            assert entity['type'] == 'formula', row
            for name in row['expected']['no_role_for']:
                c.execute("SELECT e.properties_json::jsonb->>'role' AS role, e.quality_state FROM edge e "
                          "JOIN entity n ON n.id=e.target_id WHERE e.source_id=%s AND e.relation='CONTAINS' AND n.label=%s",
                          (row['entity_id'], name))
                found = c.fetchall()
                assert found and all(r['role'] is None or r['quality_state'] == 'conflicting' for r in found), (row['id'], name)


def main():
    dev, test = load('dev'), load('test')
    frozen()
    counts(dev, test)
    query_expectations(dev + test)
    explain_expectations(dev + test)
    print('PASS: eval sets shape, frozen test hash, every expected condition and entity checked on the current batch')


if __name__ == '__main__':
    main()
