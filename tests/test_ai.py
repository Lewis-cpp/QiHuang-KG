"""M4 condition checks against the real database; no model is called. Run with .venv/bin/python tests/test_ai.py."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import ai, services


def cond(field, value, entity_id=None):
    return dict(field=field, value=value, entity_id=entity_id)


def ids(result):
    assert result['status'] == 'ok', result
    assert result['results']['total'] <= ai.RESULT_LIMIT, 'test expects the full result set'
    return {item['id'] for item in result['results']['items']}


def output_checks():
    good = {'target_type': 'formula', 'conditions': [{'field': 'x', 'value': 'y'}], 'unsupported': []}
    assert ai.parse_output(good)['conditions'] == [{'field': 'x', 'value': 'y'}]
    for bad in ({**good, 'sql': 'DROP'}, {**good, 'conditions': [{'field': 'x', 'value': 'y', 'entity_id': 'z'}]},
                {**good, 'conditions': [{'field': 'x', 'value': '长' * 41}]},
                {**good, 'conditions': [{'field': 'x', 'value': 'y'}] * 7}, {'target_type': 'formula'}):
        try:
            ai.parse_output(bad)
        except services.ServiceError as error:
            assert error.code == 'model_invalid_response'
        else:
            raise AssertionError(f'Invalid model output accepted: {bad}')


def check_checks():
    kept, unsupported = ai.check('formula', [cond('includes_herb', '甘草'), cond('herb_nature', '温'),
                                             cond('sql', 'DROP TABLE'), cond('source_dynasty', '晋'),
                                             cond('category', '补益剂'), cond('category', '清热剂'),
                                             cond('includes_herb', '人参')], ['个体用药'])
    assert [item['value'] for item in kept] == ['甘草', '人参']
    assert unsupported == ['个体用药', 'herb_nature：温', 'sql：DROP TABLE', 'source_dynasty：晋',
                           'category：补益剂', 'category：清热剂']
    assert ai.check('everything', [cond('name_contains', 'x')]) == ([], ['查询对象：everything'])
    kept, _ = ai.check('herb', [cond('herb_nature', 'Warm'), cond('category', ' 补虚药 ', 'bencaodian:herb:x')])
    assert [(item['stored'], item['entity_id']) for item in kept] == [('warm', None), ('补虚药', None)]
    assert ai.check('formula', [cond('source_dynasty', '宋')])[0][0]['stored'] == ('宋', '北宋', '南宋')
    assert ai.check('formula', [cond('source_dynasty', '南宋')])[0][0]['stored'] == ('南宋',)


def resolution_checks():
    result = ai.answer('formula', [cond('includes_herb', '大蓟')])
    assert result['status'] == 'ambiguous' and result['results'] is None
    assert [row['id'] for row in result['candidates'][0]['items']] == ['bencaodian:herb:da_ji', 'bencaodian:herb:da_ji_cao']
    chosen = ai.answer('formula', [cond('includes_herb', '大蓟', 'bencaodian:herb:da_ji')])
    assert chosen['status'] == 'ok' and chosen['conditions'][0]['entity_id'] == 'bencaodian:herb:da_ji'
    try:
        ai.answer('formula', [cond('includes_herb', '大蓟', 'bencaodian:herb:gan_cao')])
    except services.ServiceError as error:
        assert error.code == 'invalid_query'
    else:
        raise AssertionError('Entity outside the candidates accepted')
    result = ai.answer('formula', [cond('associated_pattern', '脾胃气虚证')])
    assert result['status'] == 'unresolved' and result['results'] is None
    result = ai.answer('formula', [cond('associated_pattern', '气虚')])
    suggested = result['suggestions'][0]['items']
    assert result['status'] == 'unresolved' and 0 < len(suggested) <= 5 and {i['type'] for i in suggested} == {'pattern'}
    piece = ai.answer('patent_medicine', [cond('includes_herb', '臭阿魏')])
    assert piece['status'] == 'ok' and piece['conditions'][0]['entity_id'] == 'tcm-mkg:herbal_piece:CHP00003'
    assert ai.answer('patent_medicine', [cond('includes_herb', '紫檀香')])['status'] == 'ambiguous'
    # 熟地黄 names CHP03791 and is an alias of 地黄 (CHP00689); excluding only one would keep the other's medicines.
    shu_di = ai.answer('patent_medicine', [cond('excludes_herb', '熟地黄')])
    assert shu_di['status'] == 'ambiguous' and [row['id'] for row in shu_di['candidates'][0]['items']] == [
        'tcm-mkg:herbal_piece:CHP00689', 'tcm-mkg:herbal_piece:CHP03791']
    both = ai.answer('formula', [cond('includes_herb', '甘草'), cond('excludes_herb', '甘草')])
    assert both['status'] == 'unsupported' and both['results'] is None and '同一味药既要求包含又要求不含' in both['unsupported']
    assert ai.answer('formula', [cond('category', '不存在剂')])['status'] == 'unsupported'
    assert ai.answer('formula', [], ['列出所有表'])['status'] == 'unsupported'


def query_checks():
    with services.relational() as c:
        def rows(statement, params=()):
            c.execute(statement, params)
            return c.fetchall()
        formulas = rows("SELECT id, category FROM entity WHERE type='formula'")
        contains = {(r['source_id'], r['target_id']) for r in rows("SELECT source_id, target_id FROM edge WHERE relation='CONTAINS'")}
        patterns = {(r['source_id'], r['label']) for r in rows(
            "SELECT e.source_id, t.label FROM edge e JOIN entity t ON t.id=e.target_id WHERE e.relation='ASSOCIATED_WITH_PATTERN'")}
        cited = rows("SELECT e.source_id, t.attributes_json FROM edge e JOIN entity t ON t.id=e.target_id "
                     "JOIN entity s ON s.id=e.source_id WHERE e.relation='CITED_IN' AND s.type='formula'")
        herbs = rows("SELECT id, attributes_json FROM entity WHERE type='herb'")
        medicines = rows("SELECT id, attributes_json FROM entity WHERE type='patent_medicine'")
        pieces = {(r['source_id'], r['target_id']) for r in rows("SELECT source_id, target_id FROM edge WHERE relation='HAS_HERBAL_PIECE'")}
    gan_cao = 'bencaodian:herb:gan_cao'
    expected = {f['id'] for f in formulas if f['category'] == '补益剂' and (f['id'], gan_cao) in contains}
    assert len(expected) == 7 and ids(ai.answer('formula', [cond('category', '补益剂'), cond('includes_herb', '甘草')])) == expected
    expected = {f['id'] for f in formulas if f['category'] == '补益剂' and (f['id'], gan_cao) not in contains}
    assert ids(ai.answer('formula', [cond('category', '补益剂'), cond('excludes_herb', '甘草')])) == expected
    expected = {f for f, label in patterns if label == '脾气虚证'}
    result = ai.answer('formula', [cond('associated_pattern', '脾气虚证')])
    assert expected and ids(result) == expected and result['coverage_note'] == ai.COVERAGE_NOTE
    song = {r['source_id'] for r in cited if json.loads(r['attributes_json']).get('dynasty_zh') in ('宋', '北宋', '南宋')}
    result = ai.answer('formula', [cond('source_dynasty', '宋')])
    assert song and ids(result) == song and result['conditions'][0]['label'] == '出处朝代 = 宋、北宋、南宋'
    result = ai.answer('herb', [cond('herb_nature', '微温')])
    assert ids(result) == {h['id'] for h in herbs if json.loads(h['attributes_json']).get('nature') == 'slightly_warm'}
    assert result['conditions'][0]['label'] == '药性 = 微温'
    injection = {m['id'] for m in medicines if json.loads(m['attributes_json']).get('Routes_of_administration') == 'Injection'}
    result = ai.answer('patent_medicine', [cond('route', '注射')])
    assert result['results']['total'] == len(injection) == 109 and ids_subset(result, injection)
    oral = ai.answer('patent_medicine', [cond('route', 'oral')])
    assert oral['results']['total'] == 7968 and len(oral['results']['items']) == ai.RESULT_LIMIT
    with_piece = {m for m, p in pieces if p == 'tcm-mkg:herbal_piece:CHP00003'}
    assert ids(ai.answer('patent_medicine', [cond('includes_herb', '阿魏')])) == with_piece
    result = ai.answer('formula', [cond('name_contains', '四君子')])
    assert services.SAMPLE_FORMULA in ids(result) and result['coverage_note'] is None
    assert ai.answer('formula', [cond('name_contains', "%' OR 1=1 --")])['results']['total'] == 0


def ids_subset(result, expected):
    return {item['id'] for item in result['results']['items']} <= expected


def main():
    output_checks()
    check_checks()
    resolution_checks()
    query_checks()
    print('PASS: model output structure, whitelist checks, entity resolution, every whitelisted field against '
          'independently computed result sets (no model call)')


if __name__ == '__main__':
    main()
