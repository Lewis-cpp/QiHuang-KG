"""Read-only detail, evidence and relation queries for the selected release."""

import json
import re
import unicodedata

from backend import services

EVIDENCE_ORDER = """CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id"""


def current_build(c):
    # Read the response version from the same snapshot as its data, not a reloaded config.
    c.execute('SELECT id FROM build')
    return c.fetchone()['id']


def require_entity(c, entity_id):
    c.execute('SELECT * FROM entity WHERE id=%s', (entity_id,))
    entity = c.fetchone()
    if entity is None:
        raise services.ServiceError('entity_not_found', '当前批次中不存在该实体')
    return entity


def evidence_page(c, entity_id, limit, offset):
    c.execute('SELECT count(*) AS total FROM evidence WHERE entity_id=%s', (entity_id,))
    total = c.fetchone()['total']
    c.execute('SELECT id,kind,field_path,excerpt,source_record_id FROM evidence WHERE entity_id=%s ORDER BY '
              + EVIDENCE_ORDER + ' LIMIT %s OFFSET %s', (entity_id, limit, offset))
    return dict(items=c.fetchall(), total=total, limit=limit, offset=offset)


COUNTERPART = {'herb': 'herbal_piece', 'herbal_piece': 'herb'}


def same_name_counterpart(c, entity):
    """The other source's herb/herbal piece with the identical name, only when the pairing is one-to-one."""
    other = COUNTERPART.get(entity['type'])
    if other is None:
        return []
    c.execute('SELECT id,type,label FROM entity WHERE name_norm=%s AND type IN (%s,%s)',
              (entity['name_norm'], entity['type'], other))
    rows = c.fetchall()
    same = [row for row in rows if row['type'] == entity['type']]
    match = [row for row in rows if row['type'] == other]
    return match if len(same) == 1 and len(match) == 1 else []


def entity_detail(entity_id, build_id=None):
    with services.relational(build_id) as c:
        build = current_build(c)
        entity = require_entity(c, entity_id)
        c.execute('SELECT id,title FROM dataset WHERE id=%s', (entity['dataset_id'],))
        dataset = c.fetchone()
        c.execute('SELECT name,source_record_id,field_path FROM alias WHERE entity_id=%s ORDER BY name_norm,name',
                  (entity_id,))
        aliases = c.fetchall()
        c.execute('SELECT relation,direction,count FROM v_entity_relation_summary WHERE entity_id=%s '
                  'ORDER BY relation COLLATE "C",direction COLLATE "C"', (entity_id,))
        summary = c.fetchall()
        evidence = evidence_page(c, entity_id, 20, 0)
        same_name = same_name_counterpart(c, entity)
    return dict(id=entity['id'], type=entity['type'], label=entity['label'], dataset=dataset,
                category=entity['category'], review_status=entity['review_status'],
                review_status_raw=entity['review_status_raw'], source_record_id=entity['source_record_id'],
                attributes=json.loads(entity['attributes_json']), aliases=aliases, relation_summary=summary,
                evidence_total=evidence['total'], evidence_preview=evidence['items'], same_name_entities=same_name, build_id=build)


def entity_evidence(entity_id, limit, offset, build_id=None):
    with services.relational(build_id) as c:
        build = current_build(c)
        require_entity(c, entity_id)
        page = evidence_page(c, entity_id, limit, offset)
    return dict(**page, build_id=build)


def json_pointer(content, pointer):
    """Resolve an RFC 6901 pointer, rejecting invalid escapes and array indices."""
    value = content
    if pointer == '':
        return value
    try:
        if not pointer.startswith('/'):
            raise ValueError()
        for token in pointer[1:].split('/'):
            if re.search(r'~(?![01])', token):
                raise ValueError()
            token = token.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', token):
                    raise ValueError()
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise ValueError()
        return value
    except (KeyError, IndexError, ValueError, TypeError):
        raise services.ServiceError('evidence_pointer_invalid', '证据定位失效，请联系数据维护人员') from None


def source_content(content_json):
    # Preserve the JSON type; an oversized record is omitted instead of returning broken JSON.
    if len(content_json.encode('utf-8')) > 64 * 1024:
        return None, True
    return json.loads(content_json), False


def node(entity):
    return {key: entity[key] for key in ('id', 'label', 'type')}


def evidence_detail(evidence_id, build_id=None):
    with services.relational(build_id) as c:
        build = current_build(c)
        c.execute('SELECT * FROM evidence WHERE id=%s', (evidence_id,))
        evidence = c.fetchone()
        if evidence is None:
            raise services.ServiceError('evidence_not_found', '当前批次中不存在该证据')
        c.execute('SELECT * FROM source_record WHERE id=%s', (evidence['source_record_id'],))
        source = c.fetchone()
        c.execute('SELECT * FROM dataset WHERE id=%s', (source['dataset_id'],))
        dataset = c.fetchone()
        content_json = source.pop('content_json')
        raw_value = json_pointer(json.loads(content_json), evidence['field_path'])
        source['content'], source['content_truncated'] = source_content(content_json)
        source['filename'] = source['filename'].replace('\\', '/').rsplit('/', 1)[-1]
        if evidence['entity_id'] is not None:
            target = dict(kind='entity', entity=node(require_entity(c, evidence['entity_id'])))
        else:
            c.execute('SELECT id,relation,source_id,target_id FROM edge WHERE id=%s', (evidence['edge_id'],))
            edge = c.fetchone()
            c.execute('SELECT id,label,type FROM entity WHERE id=ANY(%s)', ([edge['source_id'], edge['target_id']],))
            nodes = {row['id']: row for row in c.fetchall()}
            target = dict(kind='edge', edge=dict(id=edge['id'], relation=edge['relation'],
                          source=nodes[edge['source_id']], target=nodes[edge['target_id']]))
    return dict(id=evidence['id'], kind=evidence['kind'], field_path=evidence['field_path'],
                excerpt=evidence['excerpt'] if evidence['kind'] == 'source_quote' else None,
                target=target, raw_value=raw_value, source_record=source, dataset=dataset, build_id=build)


# Hops are (relation, direction) from the start entity; column names come only from this table.
TEMPLATES = {
    'formula_herbs': ('formula', [('CONTAINS', 'out')]),
    'herb_formulas': ('herb', [('CONTAINS', 'in')]),
    'formula_patterns': ('formula', [('ASSOCIATED_WITH_PATTERN', 'out')]),
    'herb_patterns_via_formula': ('herb', [('CONTAINS', 'in'), ('ASSOCIATED_WITH_PATTERN', 'out')]),
    'patent_medicine_pieces': ('patent_medicine', [('HAS_HERBAL_PIECE', 'out')]),
    'piece_patent_medicines': ('herbal_piece', [('HAS_HERBAL_PIECE', 'in')]),
    'piece_properties': ('herbal_piece', [('HAS_MEDICINAL_PROPERTY', 'out')]),
}
RELATIONS = ('CONTAINS', 'ASSOCIATED_WITH_PATTERN', 'CITED_IN', 'HAS_HERBAL_PIECE',
             'ASSOCIATED_WITH_TERM', 'MAPPED_TO_ICD11', 'HAS_MEDICINAL_PROPERTY')
ENDS = {'out': ('source_id', 'target_id'), 'in': ('target_id', 'source_id')}
TWO_HOP_NOTE = '该药出现在某方剂中，该方剂在来源数据中关联某证候'


def path_sql(hops):
    """Build the fixed join for a template; returns (FROM/WHERE clause, parameters before the entity ID)."""
    near, far = ENDS[hops[0][1]]
    joins = [f'edge e0 JOIN entity n0 ON n0.id=e0.{far}']
    for i, (relation, direction) in enumerate(hops[1:], 1):
        near_i, far_i = ENDS[direction]
        joins.append(f'JOIN edge e{i} ON e{i}.{near_i}=n{i - 1}.id AND e{i}.relation=%s '
                     f'JOIN entity n{i} ON n{i}.id=e{i}.{far_i}')
    return ' '.join(joins) + f' WHERE e0.{near}=%s AND e0.relation=%s', [r for r, _ in hops[1:]]


def path_order(hops):
    # Collation "C" compares UTF-8 bytes, i.e. code point order, whatever the database locale.
    last = len(hops) - 1
    if hops == [('HAS_MEDICINAL_PROPERTY', 'out')]:
        keys = ['n0.category COLLATE "C"', 'n0.label COLLATE "C"', 'n0.id']
    else:
        keys = [f'n{i}.label COLLATE "C"' for i in range(last, -1, -1)] + [f'n{i}.id' for i in range(last, -1, -1)]
    return ', '.join(keys)


def position_key(row):
    position = row['e0_properties'].get('position')
    return (position is None, position, row['n0_label'], row['n0_id'])


def fetch_paths(c, entity_id, hops, limit, offset):
    """Return (total, rows) where each row lists edges and neighbor nodes along the path."""
    clause, params = path_sql(hops)
    params = params + [entity_id, hops[0][0]]
    last = len(hops) - 1
    columns = ', '.join(f'e{i}.id AS e{i}_id, e{i}.source_id AS e{i}_source_id, e{i}.target_id AS e{i}_target_id, '
                        f'e{i}.relation AS e{i}_relation, e{i}.properties_json AS e{i}_properties_json, '
                        f'e{i}.quality_state AS e{i}_quality_state, n{i}.id AS n{i}_id, n{i}.label AS n{i}_label, '
                        f'n{i}.type AS n{i}_type, n{i}.category AS n{i}_category' for i in range(last + 1))
    if hops == [('CONTAINS', 'out')]:
        # Composition order lives in properties JSON; a formula has at most a few dozen herbs.
        # Python string order is code point order, matching COLLATE "C" below.
        c.execute('SELECT ' + columns + ' FROM ' + clause, params)
        rows = parsed(c.fetchall(), last)
        rows.sort(key=position_key)
        return len(rows), rows[offset:offset + limit]
    c.execute('SELECT count(*) AS total FROM ' + clause, params)
    total = c.fetchone()['total']
    c.execute('SELECT ' + columns + ' FROM ' + clause + ' ORDER BY ' + path_order(hops) + ' LIMIT %s OFFSET %s',
              params + [limit, offset])
    return total, parsed(c.fetchall(), last)


def parsed(rows, last):
    for row in rows:
        for i in range(last + 1):
            row[f'e{i}_properties'] = json.loads(row.pop(f'e{i}_properties_json'))
    return rows


def edge_evidence(c, edge_ids):
    evidence_ids = {edge_id: [] for edge_id in edge_ids}
    if evidence_ids:
        c.execute('SELECT id,edge_id FROM evidence WHERE edge_id=ANY(%s) ORDER BY ' + EVIDENCE_ORDER,
                  (list(evidence_ids),))
        for item in c.fetchall():
            evidence_ids[item['edge_id']].append(item['id'])
    return evidence_ids


def row_edges(row, hops):
    for i in range(len(hops)):
        yield dict(id=row[f'e{i}_id'], relation=row[f'e{i}_relation'], source_id=row[f'e{i}_source_id'],
                   target_id=row[f'e{i}_target_id'], properties=row[f'e{i}_properties'],
                   quality_state=row[f'e{i}_quality_state'])


def relation_query(template, entity_id, limit, offset, build_id=None):
    expected, hops = TEMPLATES[template]
    with services.relational(build_id) as c:
        build = current_build(c)
        entity = require_entity(c, entity_id)
        if entity['type'] != expected:
            raise services.ServiceError('unsupported_entity_type', '该实体类型不适用于所选关系模板')
        total, rows = fetch_paths(c, entity_id, hops, limit, offset)
        paths, nodes, edges = [], {}, {}
        for row in rows:
            nodes[entity_id] = node(entity)
            node_ids, edge_ids = [entity_id], []
            for i, edge in enumerate(row_edges(row, hops)):
                nodes[row[f'n{i}_id']] = dict(id=row[f'n{i}_id'], label=row[f'n{i}_label'], type=row[f'n{i}_type'])
                edges[edge['id']] = edge
                node_ids.append(row[f'n{i}_id'])
                edge_ids.append(edge['id'])
            paths.append(dict(node_ids=node_ids, edge_ids=edge_ids))
        for edge_id, ids in edge_evidence(c, list(edges)).items():
            edges[edge_id]['evidence_ids'] = ids
    result = dict(template=template, entity_id=entity_id, paths=paths, nodes=nodes, edges=edges,
                  total=total, limit=limit, offset=offset, build_id=build)
    if len(hops) > 1:
        result['note'] = TWO_HOP_NOTE
    return result


def entity_relations(entity_id, relation, direction, limit, offset, build_id=None):
    """One-hop neighbors in the relational store; a relation the entity type never has is simply empty."""
    hops = [(relation, direction)]
    with services.relational(build_id) as c:
        build = current_build(c)
        require_entity(c, entity_id)
        total, rows = fetch_paths(c, entity_id, hops, limit, offset)
        evidence_ids = edge_evidence(c, [row['e0_id'] for row in rows])
        items = []
        for row in rows:
            edge = next(row_edges(row, hops))
            items.append(dict(edge=dict(id=edge['id'], relation=edge['relation'], properties=edge['properties'],
                                        quality_state=edge['quality_state'], evidence_ids=evidence_ids[edge['id']]),
                              neighbor=dict(id=row['n0_id'], type=row['n0_type'], label=row['n0_label'],
                                            category=row['n0_category'])))
    return dict(entity_id=entity_id, relation=relation, direction=direction, items=items,
                total=total, limit=limit, offset=offset, build_id=build)


# Fields copied verbatim from linked entities onto the formula page; nothing is summarized or generated.
PATTERN_NOTE_FIELDS = ('cardinal_symptoms', 'secondary_symptoms', 'tongue', 'pulse')
HERB_NOTE_FIELDS = ('contraindications_zh', 'contraindications_en', 'safety_notes_zh', 'safety_notes_en',
                    'pregnancy', 'lactation', 'pediatric', 'dosage_range')


def picked(entity, fields):
    attributes = json.loads(entity['attributes_json'])
    return {key: attributes[key] for key in fields if attributes.get(key) not in (None, '', [], {})}


def formula_notes(entity_id, build_id=None):
    """Symptoms of the formula's linked patterns and the source safety text of its herbs."""
    with services.relational(build_id) as c:
        build = current_build(c)
        if require_entity(c, entity_id)['type'] != 'formula':
            raise services.ServiceError('unsupported_entity_type', '该实体类型不适用于方剂提示')
        c.execute('SELECT e.id AS edge_id, n.id, n.label, n.attributes_json FROM edge e JOIN entity n ON n.id=e.target_id '
                  "WHERE e.source_id=%s AND e.relation='ASSOCIATED_WITH_PATTERN' ORDER BY n.label COLLATE \"C\", n.id",
                  (entity_id,))
        pattern_rows = c.fetchall()
        evidence_ids = edge_evidence(c, [row['edge_id'] for row in pattern_rows])
        patterns = [dict(id=row['id'], label=row['label'], fields=picked(row, PATTERN_NOTE_FIELDS),
                         evidence_ids=evidence_ids[row['edge_id']]) for row in pattern_rows]
        c.execute('SELECT e.properties_json, n.id, n.label, n.attributes_json FROM edge e JOIN entity n ON n.id=e.target_id '
                  "WHERE e.source_id=%s AND e.relation='CONTAINS'", (entity_id,))
        herb_rows = c.fetchall()
    for row in herb_rows:
        row['e0_properties'], row['n0_label'], row['n0_id'] = json.loads(row['properties_json']), row['label'], row['id']
    herb_rows.sort(key=position_key)
    herbs = [dict(id=row['id'], label=row['label'], fields=picked(row, HERB_NOTE_FIELDS)) for row in herb_rows]
    return dict(entity_id=entity_id, patterns=patterns, herbs=herbs, build_id=build)


def normalize_query(text):
    return unicodedata.normalize('NFKC', text).strip().casefold()


def like_escape(text):
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


# Each entity appears once with its best hit: rank, then name before alias, then the alias text.
SEARCH_HITS = """WITH hits AS (
    SELECT id AS entity_id, 'name' AS field, label AS text, name_norm AS text_norm,
           CASE WHEN name_norm=%(q)s THEN 1 WHEN name_norm LIKE %(prefix)s THEN 3 ELSE 5 END AS match_rank
    FROM entity WHERE name_norm LIKE %(sub)s
    UNION ALL
    SELECT entity_id, 'alias', name, name_norm,
           CASE WHEN name_norm=%(q)s THEN 2 WHEN name_norm LIKE %(prefix)s THEN 4 ELSE 5 END
    FROM alias WHERE name_norm LIKE %(sub)s
), best AS (
    SELECT h.*, row_number() OVER (PARTITION BY entity_id ORDER BY match_rank,
           CASE field WHEN 'name' THEN 0 ELSE 1 END, text_norm COLLATE "C", text COLLATE "C") AS pick
    FROM hits h
)
"""
SEARCH_FROM = """ FROM best b JOIN entity e ON e.id=b.entity_id WHERE b.pick=1
    AND (%(type)s::text IS NULL OR e.type=%(type)s) AND (%(dataset)s::text IS NULL OR e.dataset_id=%(dataset)s)"""
CATALOG_FROM = """ FROM entity e
    WHERE (%(type)s::text IS NULL OR e.type=%(type)s) AND (%(dataset)s::text IS NULL OR e.dataset_id=%(dataset)s)"""
ENTITY_COLUMNS = 'e.id,e.label,e.type,e.dataset_id,e.category,e.review_status'


def search_entities(query, kind=None, dataset=None, limit=20, offset=0, build_id=None):
    query = normalize_query(query)
    escaped = like_escape(query)
    params = dict(q=query, prefix=escaped + '%', sub='%' + escaped + '%', type=kind, dataset=dataset,
                  limit=limit, offset=offset)
    with services.relational(build_id) as c:
        build = current_build(c)
        if query:
            c.execute(SEARCH_HITS + 'SELECT count(*) AS total' + SEARCH_FROM, params)
            total = c.fetchone()['total']
            c.execute(SEARCH_HITS + 'SELECT ' + ENTITY_COLUMNS + ',b.field,b.text' + SEARCH_FROM +
                      ' ORDER BY b.match_rank, e.name_norm COLLATE "C", e.id LIMIT %(limit)s OFFSET %(offset)s', params)
            items = [dict(row, match=dict(field=row.pop('field'), text=row.pop('text'))) for row in c.fetchall()]
        else:
            # Empty query: the type catalog, as before ranking was added.
            c.execute('SELECT count(*) AS total' + CATALOG_FROM, params)
            total = c.fetchone()['total']
            c.execute('SELECT ' + ENTITY_COLUMNS + CATALOG_FROM +
                      ' ORDER BY e.name_norm COLLATE "C", e.id LIMIT %(limit)s OFFSET %(offset)s', params)
            items = [dict(row, match=None) for row in c.fetchall()]
    return dict(items=items, total=total, limit=limit, offset=offset, build_id=build)


def datasets(build_id=None):
    with services.relational(build_id) as c:
        build = current_build(c)
        c.execute('SELECT * FROM dataset ORDER BY id')
        rows = c.fetchall()
        counts = {row['id']: dict(entities=0, edges=0, source_records=0) for row in rows}
        # Every edge connects two entities of the same dataset; count it under its source.
        for key, statement in [('entities', 'SELECT dataset_id, count(*) AS n FROM entity GROUP BY dataset_id'),
                               ('edges', 'SELECT s.dataset_id, count(*) AS n FROM edge e JOIN entity s '
                                         'ON s.id=e.source_id GROUP BY s.dataset_id'),
                               ('source_records', 'SELECT dataset_id, count(*) AS n FROM source_record '
                                                  'GROUP BY dataset_id')]:
            c.execute(statement)
            for row in c.fetchall():
                counts[row['dataset_id']][key] = row['n']
    return dict(items=[dict(row, counts=counts[row['id']]) for row in rows], total=len(rows), build_id=build)
