"""Read-only detail, evidence and relation queries for the selected release."""

import json

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
