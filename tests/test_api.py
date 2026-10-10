"""M1a fixed acceptance samples; run with .venv/bin/python tests/test_api.py."""

import json
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


def main():
    common_errors()
    detail_checks()
    evidence_checks()
    pointer_checks()
    print('PASS: unified errors, redaction, repeatable read, snapshot guard')


if __name__ == '__main__':
    main()
