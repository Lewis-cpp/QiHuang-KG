"""M1a fixed acceptance samples; run with .venv/bin/python tests/test_api.py."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import queries, services
from backend.app import app

BUILD = '5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a'
FORMULA = 'bencaodian:formula:si_jun_zi_tang'
CONFLICT = 'bencaodian:formula:zhu_ling_tang'
GINSENG = 'bencaodian:herb:ren_shen'
LICORICE = 'bencaodian:herb:gan_cao'
BITTER = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'
ASTRAGALUS = 'tcm-mkg:herbal_piece:CHP01717'
QUOTE = 'evidence:f1e7866ee0971b80d3d27c8cb7fecf221003b29e87cf8c42d8a6947080d71cec'
REPAIR = 'evidence:cddf877aa77babf4552bf15a1790708296568cf7404c4645995f2e5eded22227'
API = '/api/v1'
client = TestClient(app, raise_server_exceptions=False)


def ok(path, **params):
    r = client.get(API + path, params=params)
    assert r.status_code == 200, (path, r.status_code, r.text)
    data = r.json()
    assert data['build_id'] == BUILD
    return data


def error(path, status, code, **params):
    r = client.get(API + path, params=params)
    assert r.status_code == status, (path, r.status_code, r.text)
    assert set(r.json()) == {'error'} and set(r.json()['error']) == {'code', 'message'}
    assert r.json()['error']['code'] == code, r.text
    assert any('\u4e00' <= c <= '\u9fff' for c in r.json()['error']['message'])
    for forbidden in ('psycopg2', 'Traceback', 'SELECT', '/home/', 'qihuang_import', 'secret-test-value'):
        assert forbidden not in r.text
    return r.json()


def common_errors():
    error('/entities', 422, 'invalid_query', limit=51)
    error('/entities', 422, 'invalid_type', type='unsupported')
    for path in ('/nope', '/entities/x/y/z', '/evidence/..%2F..%2Fconfig%2Fpostgresql.json'):
        error(path, 404, 'not_found')
    with patch.object(services, 'stats', side_effect=ValueError('secret-test-value SELECT /home/')):
        error('/stats', 500, 'internal_error')
    with services.relational() as c:
        c.execute('SHOW transaction_isolation')
        assert c.fetchone()['transaction_isolation'] == 'repeatable read'
        c.execute('SHOW transaction_read_only')
        assert c.fetchone()['transaction_read_only'] == 'on'
        c.execute('SHOW statement_timeout')
        assert c.fetchone()['statement_timeout'] == '3s'
    with patch.object(services.psycopg2, 'connect', side_effect=AssertionError('Must not connect')):
        try:
            with services.relational('0' * 64):
                raise AssertionError('Wrong snapshot accepted')
        except services.ServiceError as e:
            assert e.code == 'snapshot_changed'


def detail_checks():
    formula = ok('/entities/' + FORMULA)
    assert (formula['label'], formula['type'], formula['category'], formula['review_status'],
            formula['review_status_raw']) == ('四君子汤', 'formula', '补益剂', 'editor_reviewed', 'editor-reviewed')
    assert formula['attributes']['treatment_principle']['zh'] == '益气健脾'
    assert formula['aliases'] == []
    assert formula['relation_summary'] == [
        dict(relation='ASSOCIATED_WITH_PATTERN', direction='out', count=1),
        dict(relation='CITED_IN', direction='out', count=1), dict(relation='CONTAINS', direction='out', count=4)]
    assert formula['evidence_total'] == len(formula['evidence_preview']) == 1
    assert formula['evidence_preview'][0]['id'].startswith('evidence:dba0589b')
    assert formula['evidence_preview'][0]['kind'] == 'curated'
    assert formula['evidence_preview'][0]['field_path'] == ''
    page = ok('/entities/' + FORMULA + '/evidence')
    assert [{k: item[k] for k in ('id', 'kind', 'field_path', 'excerpt')} for item in page['items']] == formula['evidence_preview']
    herb = ok('/entities/' + GINSENG)
    assert herb['relation_summary'] == [dict(relation='CITED_IN', direction='out', count=1),
                                         dict(relation='CONTAINS', direction='in', count=21)]
    assert herb['evidence_total'] == 2 and herb['evidence_preview'][0]['kind'] == 'source_quote'
    high = ok('/entities/' + BITTER)
    assert high['evidence_total'] == 3439 and len(high['evidence_preview']) == 20
    assert high['relation_summary'] == [dict(relation='HAS_MEDICINAL_PROPERTY', direction='in', count=3439)]
    assert len(client.get(API + '/entities/' + BITTER).content) < 50 * 1024
    repair = ok('/entities/' + ASTRAGALUS)
    assert [a['name'] for a in repair['aliases']] == ['沙苑子', '炙黄芪', '生黄芪', '白芪', '膜荚黄芪', '蒙古黄芪', '蜜芪', '蜜黄芪', '黄耆']
    assert repair['dataset']['id'] == 'tcm-mkg' and repair['review_status'] == 'unknown'
    ids = [FORMULA, GINSENG, ASTRAGALUS, BITTER, 'tcm-mkg:icd11_code:1A00',
           'tcm-mkg:patent_medicine:CPM00001', 'bencaodian:pattern:da_chang_jin_ye_kui_xu',
           'tcm-mkg:tcm_term:TCMT00001', 'bencaodian:text:bei_ji_qian_jin_yao_fang']
    for entity in ids:
        item = ok('/entities/' + entity)
        assert isinstance(item['attributes'], dict)
        if item['type'] == 'icd11_code': assert item['attributes'] == {'code': '1A00'}
    seen = []
    for offset in range(0, 3439, 50):
        page = ok('/entities/' + BITTER + '/evidence', limit=50, offset=offset)
        assert page['total'] == 3439 and len(page['items']) <= 50
        seen += [item['id'] for item in page['items']]
    assert len(seen) == len(set(seen)) == 3439
    assert len(ok('/entities/' + BITTER + '/evidence', offset=3420)['items']) == 19
    assert ok('/entities/' + BITTER + '/evidence', offset=3439)['items'] == []
    assert ok('/entities/' + BITTER + '/evidence')['items'] == ok('/entities/' + BITTER + '/evidence')['items']
    for suffix in ('', '/evidence'):
        error('/entities/bencaodian:formula:does_not_exist' + suffix, 404, 'entity_not_found')
        ok('/entities/' + FORMULA + suffix, build_id=BUILD)
        error('/entities/' + FORMULA + suffix, 409, 'snapshot_changed', build_id='0' * 64)
        error('/entities/' + FORMULA + suffix, 422, 'invalid_query', build_id='abc')
        with patch.object(services, 'relational', side_effect=AssertionError('Must not query')):
            for entity in ('abc', 'bencaodian:unknown_type:x', 'bencaodian:formula:',
                           'bencaodian:formula:' + 'x' * 201, 'bencaodian:formula:a%20b',
                           "bencaodian:formula:x' OR '1'='1", "bencaodian:formula:x%27%20OR%20%271%27=%271"):
                error('/entities/' + entity + suffix, 422, 'invalid_query')
    for params in ({'limit': 0}, {'limit': 51}, {'offset': -1}, {'offset': 10001}):
        error('/entities/' + FORMULA + '/evidence', 422, 'invalid_query', **params)


COMPOSITION = 'evidence:72340d34a2f1acaf0dee984198dcb9ea60beda6d11d8168122cecd6c1f19e33c'
# The IDs below are fixed from the acceptance release, never discovered during a test.
WHOLE = 'evidence:cf0907925b8fd3f4833665d5d7e13408733e9d3d33747a9d38cb45c9a162c9ef'


def evidence_checks():
    composition = ok('/evidence/' + COMPOSITION)
    assert composition['target']['kind'] == 'edge'
    edge = composition['target']['edge']
    assert (edge['source']['label'], edge['target']['label'], edge['relation']) == ('四君子汤', '人参', 'CONTAINS')
    assert (composition['raw_value']['role'], composition['raw_value']['dosage']) == ('jun', '9g')
    assert composition['source_record']['filename'] == 'formulas.json'
    assert composition['source_record']['record_key'] == 'si_jun_zi_tang'
    assert composition['dataset']['id'] == 'bencaodian' and composition['dataset']['license_statement']
    whole = ok('/evidence/' + WHOLE)
    assert whole['field_path'] == '' and whole['raw_value'] == whole['source_record']['content']
    assert whole['source_record']['filename'] == 'relationships.json'
    assert whole['raw_value'] == {'dosage': '9g', 'formula': 'si_jun_zi_tang', 'herb': 'ren_shen', 'role': 'jun'}
    quote = ok('/evidence/' + QUOTE)
    assert quote['kind'] == 'source_quote' and quote['target']['kind'] == 'entity'
    assert quote['target']['entity']['id'] == LICORICE
    assert quote['field_path'] == '/classical_references/0/passage'
    assert quote['raw_value'] == quote['excerpt'] == '味甘，平。主五脏六腑寒热邪气，坚筋骨，长肌肉，倍力，金疮肿，解毒。久服轻身延年。'
    repair = ok('/evidence/' + REPAIR)
    assert repair['raw_value']['CHP_ID'] == 'CHP01717'
    assert repair['source_record']['filename'] == 'D6_Chinese_herbal_pieces.tsv'
    assert repair['source_record']['record_locator'] == 'record:1717;lines:1718-1718'
    assert repair['source_record']['content']['repair'] == 'remove_exact_extra_empty_column_4'
    assert repair['source_record']['content_truncated'] is False
    samples = json.loads((ROOT / 'tests/fixtures/m1a-evidence.json').read_text())
    assert samples.pop('build_id') == BUILD
    for group, ids in samples.items():
        for evidence_id in ids:
            result = ok('/evidence/' + evidence_id)
            assert '/' not in result['source_record']['filename']
            assert chr(92) not in result['source_record']['filename']
            if group != 'stride':
                expected = 'source_quote' if group == 'source_quote' else 'bibliographic'
                assert result['kind'] == expected
            if group == 'bibliographic_entity': assert result['target']['kind'] == 'entity'
    error('/evidence/evidence:' + '0' * 64, 404, 'evidence_not_found')
    with patch.object(services, 'relational', side_effect=AssertionError('Must not query')):
        for evidence_id in ('evidence:123', 'evidence:' + 'A' * 64, 'edge:' + 'a' * 64):
            error('/evidence/' + evidence_id, 422, 'invalid_query')
    ok('/evidence/' + QUOTE, build_id=BUILD)
    error('/evidence/' + QUOTE, 409, 'snapshot_changed', build_id='0' * 64)
    error('/evidence/' + QUOTE, 422, 'invalid_query', build_id='abc')


def pointer_checks():
    data = {'a/b': {'~c': [None, '药']}, '~1': 'literal', '': 7, '01': 'key'}
    assert queries.json_pointer(data, '') == data
    assert queries.json_pointer(data, '/a~1b/~0c/1') == '药'
    assert queries.json_pointer(data, '/a~1b/~0c/0') is None
    assert queries.json_pointer(data, '/~01') == 'literal'
    assert queries.json_pointer(data, '/') == 7
    assert queries.json_pointer(data, '/01') == 'key'
    for pointer in ('bad', '/missing', '/~2', '/~', '/a~1b/~0c/-1', '/a~1b/~0c/01',
                    '/a~1b/~0c/-', '/a~1b/~0c/3', '/a~1b/~0c/0/x', '/a~1b/~0c/١'):
        try: queries.json_pointer(data, pointer)
        except services.ServiceError as e: assert e.code == 'evidence_pointer_invalid'
        else: raise AssertionError(pointer)
    limit = json.dumps({'x': 'a' * (65536 - 9)})
    assert len(limit.encode()) == 65536
    assert queries.source_content(limit) == (json.loads(limit), False)
    assert queries.source_content(limit.replace('a', '药', 1)) == (None, True)
    with patch.object(queries, 'json_pointer', side_effect=services.ServiceError('evidence_pointer_invalid', '证据定位失效')):
        error('/evidence/' + QUOTE, 500, 'evidence_pointer_invalid')


def relation_checks():
    result = ok('/relation-queries', template='formula_herbs', entity_id=FORMULA)
    assert result['total'] == len(result['paths']) == len(result['edges']) == 4
    assert len(result['nodes']) == 5
    expected = [('人参', 'jun', '9g', 'edge:17d8c5fd'), ('白术', 'chen', '9g', 'edge:e5c70d96'),
                ('茯苓', 'zuo', '9g', 'edge:76dd6516'), ('甘草', 'shi', '6g', 'edge:996ed534')]
    for position, (path, (label, role, dosage, prefix)) in enumerate(zip(result['paths'], expected)):
        assert path['node_ids'][0] == FORMULA
        assert result['nodes'][path['node_ids'][1]]['label'] == label
        edge = result['edges'][path['edge_ids'][0]]
        assert edge['id'].startswith(prefix)
        assert (edge['source_id'], edge['target_id']) == tuple(path['node_ids'])
        assert edge['properties'] == dict(position=position, role=role, dosage_raw=dosage,
                                          position_source='composition', missing_claim_fields=[])
        assert len(edge['evidence_ids']) == 2
        assert [ok('/evidence/' + eid)['field_path'] for eid in edge['evidence_ids']] == ['/composition/' + str(position), '']
    first = result['edges'][result['paths'][0]['edge_ids'][0]]
    assert first['evidence_ids'] == [COMPOSITION, WHOLE]
    conflict = ok('/relation-queries', template='formula_herbs', entity_id=CONFLICT)
    expected = [('猪苓', 'jun', 'consistent'), ('泽泻', None, 'conflicting'), ('茯苓', 'chen', 'consistent'),
                ('滑石', 'zuo', 'consistent'), ('阿胶', 'zuo', 'consistent')]
    for path, (label, role, quality) in zip(conflict['paths'], expected):
        edge = conflict['edges'][path['edge_ids'][0]]
        assert conflict['nodes'][path['node_ids'][1]]['label'] == label
        assert edge['properties']['role'] == role and edge['quality_state'] == quality
        if label == '泽泻':
            assert ok('/evidence/' + edge['evidence_ids'][0])['target']['edge']['target']['label'] == '泽泻'
    reverse = ok('/relation-queries', template='herb_formulas', entity_id=GINSENG, limit=50)
    assert reverse['total'] == len(reverse['paths']) == 21
    for path in reverse['paths']:
        assert path['node_ids'][0] == GINSENG
        edge = reverse['edges'][path['edge_ids'][0]]
        assert edge['target_id'] == GINSENG and edge['source_id'] == path['node_ids'][1]
    rows = []
    for offset in (0, 20, 40, 60):
        page = ok('/relation-queries', template='herb_formulas', entity_id=LICORICE, offset=offset)
        assert page['total'] == 61 and len(page['paths']) == (1 if offset == 60 else 20)
        assert set(page['nodes']) == {n for path in page['paths'] for n in path['node_ids']}
        assert set(page['edges']) == {e for path in page['paths'] for e in path['edge_ids']}
        rows += [(page['nodes'][p['node_ids'][1]]['label'], p['node_ids'][1]) for p in page['paths']]
    assert len(rows) == len(set(rows)) == 61 and rows == sorted(rows)
    empty = ok('/relation-queries', template='herb_formulas', entity_id=LICORICE, offset=61)
    assert empty['paths'] == [] and empty['nodes'] == empty['edges'] == {}
    for template, entity in [('formula_herbs', GINSENG), ('herb_formulas', FORMULA)]:
        error('/relation-queries', 422, 'unsupported_entity_type', template=template, entity_id=entity)
    error('/relation-queries', 404, 'entity_not_found', template='formula_herbs', entity_id='bencaodian:formula:does_not_exist')
    error('/relation-queries', 422, 'invalid_query', entity_id=FORMULA)
    with patch.object(services, 'relational', side_effect=AssertionError('Must not query')):
        for template in ('formula_patterns', '', "formula_herbs' OR 1=1"):
            error('/relation-queries', 422, 'invalid_query', template=template, entity_id=FORMULA)
        for entity in ('abc', 'tcm-mkg:unknown:x', 'bencaodian:formula:', 'bencaodian:formula:' + 'x' * 161,
                       "bencaodian:formula:x' OR '1'='1"):
            error('/relation-queries', 422, 'invalid_query', template='formula_herbs', entity_id=entity)
    params = dict(template='formula_herbs', entity_id=FORMULA)
    for invalid in ({'limit': 0}, {'limit': 51}, {'offset': -1}, {'offset': 10001}, {'build_id': 'abc'}):
        error('/relation-queries', 422, 'invalid_query', **params, **invalid)
    error('/relation-queries', 409, 'snapshot_changed', **params, build_id='0' * 64)
    ok('/relation-queries', **params, build_id=BUILD)
    # Reproduce the user-facing chain against the same real database.
    found = ok('/entities', q='四君子汤', type='formula')['items'][0]['id']
    assert ok('/entities/' + found)['id'] == FORMULA
    path = ok('/relation-queries', template='formula_herbs', entity_id=found)
    evidence = path['edges'][path['paths'][0]['edge_ids'][0]]['evidence_ids'][0]
    assert ok('/evidence/' + evidence)['raw_value']['herb_key'] == 'ren_shen'


def outage_checks():
    # Opt-in only: this check stops the local development database temporarily.
    import httpx
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=10) as http:
        assert http.get(API + '/health').status_code == 200
        requests = [('/entities/' + FORMULA, {}), ('/entities/' + FORMULA + '/evidence', {}),
                    ('/evidence/' + QUOTE, {}),
                    ('/relation-queries', dict(template='formula_herbs', entity_id=FORMULA))]
        results = []
        try:
            subprocess.run(['docker', 'compose', 'stop', '-t', '3', 'postgres'], cwd=ROOT, check=True)
            for path, params in requests:
                response = http.get(API + path, params=params)
                assert response.status_code == 503
                assert response.json() == {'error': {'code': 'database_unavailable', 'message': '关系数据库暂时不可用'}}
                results.append(dict(path=path, status=response.status_code, body=response.json()))
            assert http.get(API + '/health/live').status_code == 200
        finally:
            subprocess.run(['docker', 'compose', 'up', '-d', '--wait', 'postgres'], cwd=ROOT, check=True)
        for path, params in requests:
            response = http.get(API + path, params=params)
            assert response.status_code == 200 and response.json()['build_id'] == BUILD
        assert http.get(API + '/health').status_code == 200
    (ROOT / 'var/m1a-outage.json').write_text(json.dumps(dict(failures=results, recovered=True,
            backend_restarted=False), ensure_ascii=False, indent=2) + chr(10))
    print('PASS: E-14/E-15 actual PostgreSQL outage, live endpoint, automatic recovery without backend restart')


def openapi_checks():
    schema = client.get('/openapi.json').json()
    for path in ('/entities/{id}', '/entities/{id}/evidence', '/evidence/{id}', '/relation-queries'):
        endpoint = schema['paths'][API + path]['get']
        assert endpoint['responses']['200']['content']['application/json']['schema']['$ref']
        assert all(p.get('description') for p in endpoint['parameters'])
        assert any(p['name'] == 'build_id' for p in endpoint['parameters'])
        assert endpoint['responses']['422']['content']['application/json']['schema']['$ref'].endswith('/ErrorResponse')
    assert client.get('/docs').status_code == 200


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-outage', action='store_true', help='Temporarily stop local PostgreSQL; needs API on :8000')
    args = parser.parse_args()
    common_errors()
    detail_checks()
    evidence_checks()
    pointer_checks()
    relation_checks()
    openapi_checks()
    if args.with_outage: outage_checks()
    print('PASS: F-01–F-24 fixed data, 3439 paged IDs, 231 evidence samples, E/S boundaries, pointer and size guards')


if __name__ == '__main__':
    main()
