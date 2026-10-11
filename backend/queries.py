"""Read-only detail, evidence and relation queries for the selected release."""

import json
import re

from backend import services

EVIDENCE_ORDER = """CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path, id"""


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


def entity_detail(entity_id, build_id=None):
    with services.relational(build_id) as c:
        build = current_build(c)
        entity = require_entity(c, entity_id)
        c.execute('SELECT id,title FROM dataset WHERE id=%s', (entity['dataset_id'],))
        dataset = c.fetchone()
        c.execute('SELECT name,source_record_id,field_path FROM alias WHERE entity_id=%s ORDER BY name_norm,name',
                  (entity_id,))
        aliases = c.fetchall()
        c.execute("SELECT relation,'out' AS direction,count(*) AS count FROM edge WHERE source_id=%s GROUP BY relation "
                  "UNION ALL SELECT relation,'in' AS direction,count(*) AS count FROM edge WHERE target_id=%s "
                  'GROUP BY relation ORDER BY relation,direction', (entity_id, entity_id))
        summary = c.fetchall()
        evidence = evidence_page(c, entity_id, 20, 0)
    return dict(id=entity['id'], type=entity['type'], label=entity['label'], dataset=dataset,
                category=entity['category'], review_status=entity['review_status'],
                review_status_raw=entity['review_status_raw'], source_record_id=entity['source_record_id'],
                attributes=json.loads(entity['attributes_json']), aliases=aliases, relation_summary=summary,
                evidence_total=evidence['total'], evidence_preview=evidence['items'], build_id=build)


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


RELATION_SQL = {
    'formula_herbs': "SELECT e.*,n.id AS node_id,n.label,n.type FROM edge e JOIN entity n ON n.id=e.target_id "
                     "WHERE e.source_id=%s AND e.relation='CONTAINS'",
    'herb_formulas': "SELECT e.*,n.id AS node_id,n.label,n.type FROM edge e JOIN entity n ON n.id=e.source_id "
                     "WHERE e.target_id=%s AND e.relation='CONTAINS' ORDER BY n.label,n.id",
}


def relation_query(template, entity_id, limit, offset, build_id=None):
    with services.relational(build_id) as c:
        build = current_build(c)
        entity = require_entity(c, entity_id)
        expected = 'formula' if template == 'formula_herbs' else 'herb'
        if entity['type'] != expected:
            raise services.ServiceError('unsupported_entity_type', '该实体类型不适用于所选关系模板')
        c.execute(RELATION_SQL[template], (entity_id,))
        rows = c.fetchall()
        for row in rows:
            row['properties'] = json.loads(row.pop('properties_json'))
        # shortcut: these templates have at most 61 matches; move paging into SQL if this grows.
        if template == 'formula_herbs':
            rows.sort(key=lambda r: (r['properties'].get('position') is None,
                                    r['properties'].get('position'), r['label'], r['node_id']))
        total = len(rows)
        page = rows[offset:offset + limit]
        evidence_ids = {row['id']: [] for row in page}
        if page:
            c.execute('SELECT id,edge_id FROM evidence WHERE edge_id=ANY(%s) ORDER BY ' + EVIDENCE_ORDER,
                      (list(evidence_ids),))
            for item in c.fetchall():
                evidence_ids[item['edge_id']].append(item['id'])
        paths, nodes, edges = [], {}, {}
        for row in page:
            nodes[entity_id] = node(entity)
            nodes[row['node_id']] = dict(id=row['node_id'], label=row['label'], type=row['type'])
            edges[row['id']] = {key: row[key] for key in
                               ('id', 'relation', 'source_id', 'target_id', 'properties', 'quality_state')}
            edges[row['id']]['evidence_ids'] = evidence_ids[row['id']]
            paths.append(dict(node_ids=[entity_id, row['node_id']], edge_ids=[row['id']]))
    return dict(template=template, entity_id=entity_id, paths=paths, nodes=nodes, edges=edges,
                total=total, limit=limit, offset=offset, build_id=build)
