"""M4 AI query: whitelist checks, entity resolution and parameterized SQL over model-proposed conditions."""

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend import queries, services, vocab

TARGETS = ('formula', 'herb', 'patent_medicine', 'herbal_piece')
# Field → target types it applies to (spec §7.1); any other combination is unsupported.
FIELDS = {
    'name_contains': TARGETS, 'category': ('formula', 'herb'),
    'includes_herb': ('formula', 'patent_medicine'), 'excludes_herb': ('formula', 'patent_medicine'),
    'associated_pattern': ('formula',), 'source_dynasty': ('formula',),
    'herb_nature': ('herb',), 'route': ('patent_medicine',),
}
LABELS = {
    'name_contains': '名称包含 {}', 'category': '分类 = {}', 'includes_herb': '包含 {}', 'excludes_herb': '不含 {}',
    'associated_pattern': '关联证候 = {}', 'source_dynasty': '出处朝代 = {}', 'herb_nature': '药性 = {}',
    'route': '给药途径 = {}',
}
HERB_FIELDS = ('includes_herb', 'excludes_herb')
ENTITY_FIELDS = HERB_FIELDS + ('associated_pattern',)
HERB_LINKS = {'formula': ('CONTAINS', 'herb'), 'patent_medicine': ('HAS_HERBAL_PIECE', 'herbal_piece')}
ENUMS = {'herb_nature': (vocab.NATURE_V1, 'nature'), 'route': (vocab.ROUTE_V1, 'Routes_of_administration')}
RESULT_LIMIT = 50
COVERAGE_NOTE = '出处朝代覆盖本草典 112 首方剂；证候关联仅覆盖其中 56 首。'


class Condition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    value: str = Field(min_length=1, max_length=40)


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_type: str
    conditions: list[Condition] = Field(max_length=6)
    unsupported: list[str]


def parse_output(data):
    """The model's JSON as plain dicts; only a broken structure fails, unknown names are handled by check()."""
    try:
        return ModelOutput.model_validate(data).model_dump()
    except ValidationError:
        raise services.ServiceError('model_invalid_response', '模型响应不符合 JSON 接口约定') from None


def link(field, target_type):
    """(relation, entity type) an entity-valued field resolves against."""
    return ('ASSOCIATED_WITH_PATTERN', 'pattern') if field == 'associated_pattern' else HERB_LINKS[target_type]


def stored_value(field, value):
    if field == 'source_dynasty':
        return vocab.dynasty(value)
    if field in ENUMS:
        return vocab.enum(ENUMS[field][0], value)
    return value


def check(target_type, conditions, unsupported=()):
    """Split conditions into whitelisted ones with stored values, and unsupported descriptions."""
    unsupported = list(unsupported)
    if target_type not in TARGETS:
        return [], unsupported + [f'查询对象：{target_type}']
    counts = Counter(item['field'] for item in conditions)
    kept = []
    for item in conditions:
        field, value = item['field'], item['value'].strip()
        stored = stored_value(field, value) if value else None
        # A repeated single-valued field has no defined meaning; drop every copy rather than pick one.
        if target_type not in FIELDS.get(field, ()) or stored is None or (counts[field] > 1 and field not in HERB_FIELDS):
            unsupported.append(f'{field}：{value}')
        else:
            kept.append(dict(field=field, value=value, stored=stored,
                             entity_id=item.get('entity_id') if field in ENTITY_FIELDS else None))
    return kept, unsupported


def label(item):
    field, stored = item['field'], item['stored']
    if field == 'source_dynasty':
        shown = '、'.join(stored)
    elif field in ENUMS:
        shown = vocab.chinese(ENUMS[field][0], stored)
    else:
        shown = item['value']
    return LABELS[field].format(shown)


def categories(c, target_type):
    c.execute('SELECT category FROM entity WHERE type=%s AND category IS NOT NULL GROUP BY category '
              'ORDER BY category COLLATE "C"', (target_type,))
    return [row['category'] for row in c.fetchall()]


def candidates(c, kind, value):
    """Entities of one type whose name or alias is exactly `value`; 熟地黄 is one piece's name and another's alias."""
    norm = queries.normalize_query(value)
    c.execute('SELECT ' + queries.ENTITY_COLUMNS + ' FROM entity e WHERE e.type=%s AND (e.name_norm=%s OR EXISTS '
              '(SELECT 1 FROM alias a WHERE a.entity_id=e.id AND a.name_norm=%s)) ORDER BY e.id', (kind, norm, norm))
    return c.fetchall()


def fragment(target_type, item):
    """A fixed SQL condition on entity e and its bound parameters; no condition text enters the SQL."""
    field = item['field']
    if field == 'name_contains':
        sub = '%' + queries.like_escape(queries.normalize_query(item['value'])) + '%'
        return ('(e.name_norm LIKE %s OR EXISTS (SELECT 1 FROM alias a WHERE a.entity_id=e.id AND a.name_norm LIKE %s))',
                [sub, sub])
    if field == 'category':
        return 'e.category=%s', [item['stored']]
    if field in ENTITY_FIELDS:
        clause = 'EXISTS (SELECT 1 FROM edge x WHERE x.source_id=e.id AND x.relation=%s AND x.target_id=%s)'
        return ('NOT ' if field == 'excludes_herb' else '') + clause, [link(field, target_type)[0], item['entity_id']]
    # shortcut: attributes_json is parsed per row (365 herbs, ~9,000 patent medicines); index it if M5 timings need.
    if field == 'source_dynasty':
        return ("EXISTS (SELECT 1 FROM edge x JOIN entity t ON t.id=x.target_id WHERE x.source_id=e.id "
                "AND x.relation='CITED_IN' AND t.attributes_json::jsonb->>'dynasty_zh'=ANY(%s))", [list(item['stored'])])
    return 'e.attributes_json::jsonb->>%s=%s', [ENUMS[field][1], item['stored']]


def run(c, target_type, conditions):
    clauses, params = ['e.type=%s'], [target_type]
    for item in conditions:
        clause, values = fragment(target_type, item)
        clauses.append(clause)
        params += values
    where = ' FROM entity e WHERE ' + ' AND '.join(clauses)
    c.execute('SELECT count(*) AS total' + where, params)
    total = c.fetchone()['total']
    c.execute('SELECT ' + queries.ENTITY_COLUMNS + where + ' ORDER BY e.name_norm COLLATE "C", e.id LIMIT %s',
              params + [RESULT_LIMIT])
    return dict(items=[dict(row, match=None) for row in c.fetchall()], total=total)


def answer(target_type, conditions, unsupported=(), build_id=None):
    """Check, resolve and run conditions; the /ai/query response fields other than model metadata.

    A condition may carry the entity_id chosen after disambiguation; it must be one of the value's candidates.
    """
    kept, unsupported = check(target_type, conditions, unsupported)
    result = dict(status='unsupported', target_type=target_type, conditions=[], unsupported=unsupported,
                  candidates=None, suggestions=None, coverage_note=None, results=None)
    with services.relational(build_id) as c:
        result['build_id'] = queries.current_build(c)
        resolved, ambiguous, missing = [], [], []
        for item in kept:
            if item['field'] == 'category' and item['stored'] not in categories(c, target_type):
                unsupported.append(f"category：{item['value']}")
                continue
            if item['field'] in ENTITY_FIELDS:
                kind = link(item['field'], target_type)[1]
                rows = candidates(c, kind, item['value'])
                if item['entity_id'] is not None:
                    rows = [row for row in rows if row['id'] == item['entity_id']]
                    if not rows:
                        raise services.ServiceError('invalid_query', f"所选实体不是“{item['value']}”的候选")
                if len(rows) == 1:
                    item['entity_id'] = rows[0]['id']
                elif rows:
                    ambiguous.append(dict(field=item['field'], value=item['value'], items=rows))
                else:
                    missing.append(dict(field=item['field'], value=item['value'],
                                        items=queries.search_page(c, item['value'], kind, limit=5)['items']))
            resolved.append(item)
        result['conditions'] = [dict(field=item['field'], value=item['value'], entity_id=item['entity_id'],
                                     label=label(item)) for item in resolved]
        result['candidates'], result['suggestions'] = ambiguous or None, missing or None
        if ambiguous or missing:
            result['status'] = 'ambiguous' if ambiguous else 'unresolved'
            return result
        chosen = {field: {item['entity_id'] for item in resolved if item['field'] == field} for field in HERB_FIELDS}
        if not resolved or chosen['includes_herb'] & chosen['excludes_herb']:
            if resolved:
                unsupported.append('同一味药既要求包含又要求不含')
            return result
        result['results'] = run(c, target_type, resolved)
    if any(item['field'] in ('source_dynasty', 'associated_pattern') for item in resolved):
        result['coverage_note'] = COVERAGE_NOTE
    result['status'] = 'ok'
    return result
