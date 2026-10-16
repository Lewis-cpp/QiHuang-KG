"""M1a and M1b fixed acceptance samples; run with .venv/bin/python tests/test_api.py."""

import argparse
import io
import json
import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import queries, services
from backend.app import app

BUILD = 'cbadd11ea5c86dc3d7654c4652b06e23a77245af728fee2f1c46c9382ced867e'
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
    method = client.post(API + '/entities')
    assert method.status_code == 405 and method.json()['error']['code'] == 'method_not_allowed'
    assert method.headers['allow'] == 'GET'
    error('/entities', 422, 'invalid_query', limit=51)
    error('/entities', 422, 'invalid_type', type='unsupported')
    for path in ('/nope', '/entities/x/y/z', '/evidence/..%2F..%2Fconfig%2Fpostgresql.json'):
        error(path, 404, 'not_found')
    log = io.StringIO()
    handler = logging.StreamHandler(log)
    logger = logging.getLogger('backend.app')
    logger.addHandler(handler)
    try:
        with patch.object(services, 'stats', side_effect=ValueError('secret-test-value SELECT /home/')):
            error('/stats', 500, 'internal_error')
        assert log.getvalue().strip() == 'Unhandled API exception: ValueError'
    finally:
        logger.removeHandler(handler)
        handler.close()
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
        for template in ('formula_pattern', '', "formula_herbs' OR 1=1"):
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


def ordering_checks():
    # Existing Chinese names do not distinguish locale order from code point order.
    rows = [dict(e0_id='edge:' + key, e0_source_id=FORMULA, e0_target_id=key, e0_relation='CONTAINS',
                 e0_properties_json=json.dumps(properties), e0_quality_state='consistent', n0_id=key, n0_label=label,
                 n0_type='herb', n0_category=None)
            for key, label, properties in [('e', 'A', {}), ('d', 'ä', {'position': 0}), ('c', 'z', {'position': 0}),
                                           ('b', 'A', {'position': 0}), ('a', 'A', {'position': 0})]]
    for offset, expected in [(0, ['a', 'b']), (2, ['c', 'd']), (4, ['e'])]:
        with patch.object(services, 'relational') as relational:
            c = relational.return_value.__enter__.return_value
            c.fetchone.side_effect = [{'id': BUILD}, dict(id=FORMULA, label='四君子汤', type='formula')]
            c.fetchall.side_effect = [[dict(row) for row in rows], []]
            page = queries.relation_query('formula_herbs', FORMULA, 2, offset)
        assert page['total'] == 5
        assert [p['node_ids'][1] for p in page['paths']] == expected
    with services.relational() as c:
        c.execute("SELECT collname FROM pg_collation WHERE collname='en-US-x-icu'")
        if c.fetchone() is None:
            print('SKIP: locale comparison needs PostgreSQL en-US-x-icu collation')
            return
        source = """SELECT field_path COLLATE "en-US-x-icu" AS field_path, 'curated' AS kind, 'id' AS id
                    FROM unnest(%s::text[]) AS field_path"""
        paths = ['/ab', '/a', '/A', '/a-b', '']
        c.execute('SELECT field_path FROM (' + source + ') sample ORDER BY ' + queries.EVIDENCE_ORDER, (paths,))
        assert [r['field_path'] for r in c.fetchall()] == ['/A', '/a', '/a-b', '/ab', '']
        # SQL-paged templates must not follow the database locale either.
        labels = ['ä', 'z', 'A', 'a', 'B']
        for template in ('herb_formulas', 'piece_properties', 'herb_patterns_via_formula'):
            hops = queries.TEMPLATES[template][1]
            joins = ' CROSS JOIN LATERAL '.join(
                f'(SELECT x.v COLLATE "en-US-x-icu" AS label, x.v AS id, x.v COLLATE "en-US-x-icu" AS category) n{i}'
                for i in range(len(hops)))
            c.execute('SELECT n0.id FROM unnest(%s::text[]) AS x(v) CROSS JOIN LATERAL ' + joins
                      + ' ORDER BY ' + queries.path_order(hops), (labels,))
            assert [r['id'] for r in c.fetchall()] == ['A', 'B', 'a', 'z', 'ä'], template


PIECE_LICORICE = 'tcm-mkg:herbal_piece:CHP01118'
PATENT = 'tcm-mkg:patent_medicine:CPM00001'


def search_checks():
    exact = ok('/entities', q='甘草', limit=50)
    assert exact['total'] == 18
    assert [(i['label'], i['type']) for i in exact['items'][:2]] == [('甘草', 'herb'), ('甘草', 'herbal_piece')]
    assert all(i['match'] == dict(field='name', text=i['label']) for i in exact['items'][:7])
    assert [i['label'] for i in exact['items'][2:7]] == ['甘草头', '甘草梢', '甘草流浸膏', '甘草浸膏', '甘草节']
    assert exact['items'][7]['label'] == '云南甘草'
    assert len({i['id'] for i in exact['items']}) == 18
    # Alias exact (rank 2) precedes name prefix (rank 3); one entity appears once despite nine aliases.
    alias = ok('/entities', q='黄耆')
    assert [(i['id'], i['match']) for i in alias['items']] == [
        (ASTRAGALUS, dict(field='alias', text='黄耆')),
        ('tcm-mkg:herbal_piece:CHP01718', dict(field='alias', text='黄耆茎叶')),
        ('tcm-mkg:herbal_piece:CHP03978', dict(field='name', text='苏黄耆'))]
    assert ok('/entities', q='  ＢＩＴＴＥＲ  ')['items'][0]['id'] == BITTER
    # LIKE wildcards are literal: one source alias really contains an underscore.
    assert ok('/entities', q='%')['total'] == 0
    underscore = ok('/entities', q='_')
    assert underscore['total'] == 1 and '_' in underscore['items'][0]['match']['text']
    assert ok('/entities', q='甘草', dataset='bencaodian')['total'] == 2
    assert all(i['dataset_id'] == 'tcm-mkg' for i in ok('/entities', q='甘草', dataset='tcm-mkg', limit=50)['items'])
    assert ok('/entities', q='甘草', type='formula', dataset='tcm-mkg')['items'] == []
    catalog = ok('/entities', type='medicinal_property', limit=50)
    assert catalog['total'] == 23 and all(i['match'] is None for i in catalog['items'])
    assert ok('/entities')['total'] == 20374
    seen = []
    for offset in range(0, 871, 50):
        page = ok('/entities', q='草', limit=50, offset=offset)
        assert page['total'] == 871
        seen += [i['id'] for i in page['items']]
    assert len(seen) == len(set(seen)) == 871
    error('/entities', 422, 'invalid_query', dataset='other')
    error('/entities', 422, 'invalid_query', q='x' * 101)
    error('/entities', 409, 'snapshot_changed', q='甘草', build_id='0' * 64)


def neighbor_checks():
    path = '/entities/' + CONFLICT + '/relations'
    composition = ok(path, relation='CONTAINS', direction='out')
    assert composition['total'] == 5
    assert [(i['neighbor']['label'], i['edge']['properties']['role'], i['edge']['quality_state'])
            for i in composition['items']] == [('猪苓', 'jun', 'consistent'), ('泽泻', None, 'conflicting'),
                                                 ('茯苓', 'chen', 'consistent'), ('滑石', 'zuo', 'consistent'),
                                                 ('阿胶', 'zuo', 'consistent')]
    template = ok('/relation-queries', template='formula_herbs', entity_id=CONFLICT)
    assert [i['edge']['id'] for i in composition['items']] == [p['edge_ids'][0] for p in template['paths']]
    assert all(i['edge']['evidence_ids'] == template['edges'][i['edge']['id']]['evidence_ids']
               for i in composition['items'])
    reverse = ok('/entities/' + LICORICE + '/relations', relation='CONTAINS', direction='in', limit=50, offset=50)
    assert reverse['total'] == 61 and len(reverse['items']) == 11
    properties = ok('/entities/' + ASTRAGALUS + '/relations', relation='HAS_MEDICINAL_PROPERTY', direction='out')
    assert [(i['neighbor']['category'], i['neighbor']['label']) for i in properties['items']] == [
        ('Medicinal flavor', 'Sweet medicinal'), ('Meridian tropism', 'Lung meridian'),
        ('Meridian tropism', 'Spleen meridian'), ('Therapeutic nature', 'Warm therapeutic')]
    seen = []
    for offset in range(0, 3439, 50):
        page = ok('/entities/' + BITTER + '/relations', relation='HAS_MEDICINAL_PROPERTY', direction='in',
                  limit=50, offset=offset)
        assert page['total'] == 3439
        seen += [(i['neighbor']['label'], i['neighbor']['id']) for i in page['items']]
    assert len(seen) == len(set(seen)) == 3439 and seen == sorted(seen)
    assert ok('/entities/' + BITTER + '/relations', relation='HAS_MEDICINAL_PROPERTY', direction='in',
              offset=3439)['items'] == []
    # A relation the entity type never has is an empty result, not an error.
    empty = ok('/entities/' + GINSENG + '/relations', relation='HAS_HERBAL_PIECE', direction='out')
    assert empty['items'] == [] and empty['total'] == 0
    error('/entities/bencaodian:herb:does_not_exist/relations', 404, 'entity_not_found',
          relation='CONTAINS', direction='in')
    with patch.object(services, 'relational', side_effect=AssertionError('Must not query')):
        for params in (dict(direction='out'), dict(relation='CONTAINS'), dict(relation='contains', direction='out'),
                       dict(relation='CONTAINS', direction='both'), dict(relation='CONTAINS', direction='out', limit=51),
                       dict(relation='CONTAINS', direction='out', offset=10001),
                       dict(relation='CONTAINS', direction='out', build_id='abc')):
            error(path, 422, 'invalid_query', **params)
    error(path, 409, 'snapshot_changed', relation='CONTAINS', direction='out', build_id='0' * 64)


def template_checks():
    def labels(page):
        return [[page['nodes'][n]['label'] for n in p['node_ids']] for p in page['paths']]

    def consistent(page, hops):
        assert set(page['nodes']) == {n for p in page['paths'] for n in p['node_ids']}
        assert set(page['edges']) == {e for p in page['paths'] for e in p['edge_ids']}
        for p in page['paths']:
            assert len(p['edge_ids']) == hops and len(p['node_ids']) == hops + 1
            for (a, b), edge_id in zip(zip(p['node_ids'], p['node_ids'][1:]), p['edge_ids']):
                edge = page['edges'][edge_id]
                assert {edge['source_id'], edge['target_id']} == {a, b} and edge['evidence_ids']

    patterns = ok('/relation-queries', template='formula_patterns', entity_id=CONFLICT)
    assert labels(patterns) == [['猪苓汤', '下焦湿热证'], ['猪苓汤', '肾阴虚证'], ['猪苓汤', '膀胱湿热证']]
    assert 'note' not in patterns or patterns['note'] is None
    consistent(patterns, 1)
    two_hop = ok('/relation-queries', template='herb_patterns_via_formula', entity_id=GINSENG, limit=50)
    assert two_hop['total'] == len(two_hop['paths']) == 23
    assert two_hop['note'] == '该药出现在某方剂中，该方剂在来源数据中关联某证候'
    assert labels(two_hop)[:3] == [['人参', '乌梅丸', '厥阴病证'], ['人参', '吴茱萸汤', '厥阴病证'],
                                   ['人参', '理中汤', '太阴病证']]
    # The same pattern reached through different formulas stays as separate paths.
    assert [row[1:] for row in labels(two_hop)].count(['炙甘草汤', '心气虚证']) == 1
    assert sum(row[2] == '厥阴病证' for row in labels(two_hop)) == 2
    for p in two_hop['paths']:
        first, second = (two_hop['edges'][e] for e in p['edge_ids'])
        assert (first['relation'], first['target_id'], second['relation']) == ('CONTAINS', GINSENG, 'ASSOCIATED_WITH_PATTERN')
        assert first['source_id'] == second['source_id'] == p['node_ids'][1]
    consistent(two_hop, 2)
    rows = []
    for offset in (0, 20, 40):
        page = ok('/relation-queries', template='herb_patterns_via_formula', entity_id=LICORICE, offset=offset)
        assert page['total'] == 52
        consistent(page, 2)
        rows += [(page['nodes'][p['node_ids'][2]]['label'], page['nodes'][p['node_ids'][1]]['label']) for p in page['paths']]
    assert len(rows) == len(set(rows)) == 52 and rows == sorted(rows)
    pieces = ok('/relation-queries', template='patent_medicine_pieces', entity_id=PATENT)
    assert pieces['total'] == 9 and labels(pieces)[0] == ['阿归养血胶囊', '党参']
    assert [row[1] for row in labels(pieces)] == sorted(row[1] for row in labels(pieces))
    consistent(pieces, 1)
    reverse = ok('/relation-queries', template='piece_patent_medicines', entity_id=PIECE_LICORICE, limit=50, offset=2250)
    assert reverse['total'] == 2278 and len(reverse['paths']) == 28
    consistent(reverse, 1)
    assert all(reverse['edges'][p['edge_ids'][0]]['target_id'] == PIECE_LICORICE for p in reverse['paths'])
    properties = ok('/relation-queries', template='piece_properties', entity_id=ASTRAGALUS)
    assert labels(properties) == [['黄芪', 'Sweet medicinal'], ['黄芪', 'Lung meridian'], ['黄芪', 'Spleen meridian'],
                                  ['黄芪', 'Warm therapeutic']]
    assert properties['edges'][properties['paths'][0]['edge_ids'][0]]['properties']['Class'] == 'Medicinal flavor'
    consistent(properties, 1)
    for template, entity in [('formula_patterns', GINSENG), ('herb_patterns_via_formula', FORMULA),
                             ('patent_medicine_pieces', ASTRAGALUS), ('piece_patent_medicines', PATENT),
                             ('piece_properties', GINSENG)]:
        error('/relation-queries', 422, 'unsupported_entity_type', template=template, entity_id=entity)
        empty = ok('/relation-queries', template=template, entity_id=dict(
            formula_patterns=FORMULA, herb_patterns_via_formula=GINSENG, patent_medicine_pieces=PATENT,
            piece_patent_medicines=ASTRAGALUS, piece_properties=ASTRAGALUS)[template], offset=10000)
        assert empty['paths'] == [] and empty['nodes'] == empty['edges'] == {}


def dataset_checks():
    result = ok('/datasets')
    assert [d['id'] for d in result['items']] == ['bencaodian', 'tcm-mkg'] and result['total'] == 2
    counts = {d['id']: d['counts'] for d in result['items']}
    assert counts == {'bencaodian': dict(entities=599, edges=1286, source_records=2076),
                      'tcm-mkg': dict(entities=19775, edges=178216, source_records=195211)}
    stats = ok('/stats')
    assert sum(c['entities'] for c in counts.values()) == stats['entities']
    assert sum(c['edges'] for c in counts.values()) == stats['edges']
    for d in result['items']:
        assert d['license_statement'] and d['attribution'] and d['source_url'].startswith('https://')
    ok('/datasets', build_id=BUILD)
    error('/datasets', 409, 'snapshot_changed', build_id='0' * 64)
    error('/datasets', 422, 'invalid_query', build_id='abc')


def reader_checks():
    """T11: the application role really fails to write, not merely configured read-only."""
    import psycopg2
    from psycopg2 import sql
    with services.relational() as c:
        c.execute('SELECT current_user AS role')
        assert c.fetchone()['role'] == 'qihuang_reader'
    settings = services.application()
    schema = sql.Identifier(settings['schema'])
    db = psycopg2.connect(**dict(services.config(settings['database_engine'] + '_reader'), connect_timeout=3))
    codes = {}
    try:
        with db.cursor() as c:
            c.execute('SHOW default_transaction_read_only')
            assert c.fetchone()[0] == 'on'
            try:
                c.execute(sql.SQL('UPDATE {}.entity SET label=label WHERE false').format(schema))
            except psycopg2.Error as error:
                codes['default_session_update'] = error.pgcode
            db.rollback()
            statements = dict(
                insert=sql.SQL("INSERT INTO {}.dataset VALUES ('probe','t','v','https://x','l','a')").format(schema),
                update=sql.SQL('UPDATE {}.entity SET label=label WHERE false').format(schema),
                delete=sql.SQL('DELETE FROM {}.evidence WHERE false').format(schema),
                create_table=sql.SQL('CREATE TABLE {}.reader_probe (id INTEGER)').format(schema),
                create_view=sql.SQL('CREATE VIEW {}.reader_probe AS SELECT 1 AS id').format(schema),
                create_public=sql.SQL('CREATE TABLE public.reader_probe (id INTEGER)'),
                create_schema=sql.SQL('CREATE SCHEMA reader_probe'))
            for name, statement in statements.items():
                # Lifting the session default must not help: privileges, not the setting, block writes.
                c.execute('SET TRANSACTION READ WRITE')
                try:
                    c.execute(statement)
                except psycopg2.Error as error:
                    codes[name] = error.pgcode
                db.rollback()
            c.execute(sql.SQL('SELECT count(*) FROM {}.entity').format(schema))
            assert c.fetchone()[0] == 20374
    finally:
        db.close()
    assert codes == dict(default_session_update='25006', **{name: '42501' for name in statements}), codes
    return codes


def view_checks():
    with services.relational() as c:
        c.execute('SELECT herb_label,dosage_raw,role,position,quality_state FROM v_formula_composition '
                  'WHERE formula_id=%s ORDER BY position', (CONFLICT,))
        rows = [tuple(r.values()) for r in c.fetchall()]
        c.execute('SELECT count(*) AS n FROM v_formula_composition')
        assert c.fetchone()['n'] == 751
        c.execute('SELECT count(*) AS n FROM v_formula_composition WHERE role IS NULL')
        assert c.fetchone()['n'] == 1
    assert rows == [('猪苓', '9g', 'jun', 0, 'consistent'), ('泽泻', '9g', None, 1, 'conflicting'),
                    ('茯苓', '9g', 'chen', 2, 'consistent'), ('滑石', '9g', 'zuo', 3, 'consistent'),
                    ('阿胶', '9g', 'zuo', 4, 'consistent')], rows
    composition = ok('/entities/' + CONFLICT + '/relations', relation='CONTAINS', direction='out')
    assert [i['neighbor']['label'] for i in composition['items']] == [r[0] for r in rows]


def health_checks():
    class Session:
        def __init__(self, scopes):
            self.scopes = scopes

        def run(self, query, **params):
            if 'dbms.components' in query:
                return type('Result', (), {'single': lambda _: {'version': '5.26'}})()
            assert params == {'build': BUILD}
            return [{'scope': scope} for scope in self.scopes]

    for scopes, expected in [(['bootstrap', 'full'], 'full'), (['bootstrap'], 'sample'), ([], 'not_ready')]:
        with patch.object(services, 'graph') as graph:
            graph.return_value.__enter__.return_value = Session(scopes)
            result = services.graph_health()
        assert result['projection'] == expected and result['build_id'] == (BUILD if scopes else None)
    with patch.object(services, 'graph_health', side_effect=services.ServiceError('neo4j_unavailable', '图数据库暂时不可用')):
        health = client.get(API + '/health').json()
    assert health['services']['neo4j']['projection'] == 'not_ready'


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


def formula_note_checks():
    # Copied source text only: pattern symptoms through ASSOCIATED_WITH_PATTERN, herb safety fields through CONTAINS.
    notes = ok(f'/entities/{FORMULA}/formula-notes')
    assert [(p['label'], p['evidence_ids'] != []) for p in notes['patterns']] == [('脾气虚证', True)]
    fields = notes['patterns'][0]['fields']
    assert set(fields) == {'cardinal_symptoms', 'secondary_symptoms', 'tongue', 'pulse'}
    assert fields['cardinal_symptoms'][0]['zh'] == '食少纳呆' and fields['tongue']['zh'] == '舌淡苔白'
    assert [h['label'] for h in notes['herbs']] == ['人参', '白术', '茯苓', '甘草']
    ginseng = notes['herbs'][0]
    assert ginseng['id'] == GINSENG and ginseng['fields']['contraindications_zh'].startswith('不宜与藜芦同用')
    assert set(ginseng['fields']) <= set(queries.HERB_NOTE_FIELDS)
    # No linked pattern is an empty list, not an inferred one.
    assert ok('/entities/bencaodian:formula:xue_fu_zhu_yu_tang/formula-notes')['patterns'] == []
    # 十枣汤 lists 大戟 (corrected from the source key for 大蓟) and shows its source dosage note.
    shi_zao = ok('/entities/bencaodian:formula:shi_zao_tang/formula-notes')
    assert [h['label'] for h in shi_zao['herbs']] == ['芫花', '甘遂', '大戟', '大枣']
    assert shi_zao['herbs'][2]['id'] == 'bencaodian:herb:da_ji_2'
    assert '反甘草' in shi_zao['herbs'][2]['fields']['dosage_range']['notes']
    composition = ok('/entities/bencaodian:formula:shi_zao_tang/relations', relation='CONTAINS', direction='out')
    fixes = [i['edge']['properties'].get('corrections') for i in composition['items']]
    assert [bool(f) for f in fixes] == [False, False, True, False]
    assert {f['raw_value'] for f in fixes[2]} == {'da_ji'} and len(composition['items'][2]['edge']['evidence_ids']) == 5
    assert ok('/entities/bencaodian:herb:da_ji/relations', relation='CONTAINS', direction='in')['total'] == 0
    error(f'/entities/{GINSENG}/formula-notes', 422, 'unsupported_entity_type')
    error('/entities/bencaodian:formula:nope/formula-notes', 404, 'entity_not_found')
    error(f'/entities/{FORMULA}/formula-notes', 409, 'snapshot_changed', build_id='0' * 64)


def openapi_checks():
    schema = client.get('/openapi.json').json()
    for path in ('/entities', '/entities/{id}', '/entities/{id}/evidence', '/entities/{id}/relations',
                 '/evidence/{id}', '/relation-queries', '/datasets', '/entities/{id}/formula-notes'):
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
    ordering_checks()
    search_checks()
    neighbor_checks()
    template_checks()
    dataset_checks()
    formula_note_checks()
    view_checks()
    health_checks()
    reader_checks()
    openapi_checks()
    if args.with_outage: outage_checks()
    print('PASS: F-01–F-24 fixed data, 3439 paged IDs, 231 evidence samples, E/S boundaries, pointer and size guards; '
          'M1b ranked search, neighbor paging, seven templates, dataset catalog, business views, projection states, '
          'read-only role write failures (42501)')


if __name__ == '__main__':
    main()
