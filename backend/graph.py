"""One-hop graph neighborhoods read from the Neo4j projection (spec §6.2)."""

from backend import queries, services

MAX_NODES = 50
MAX_EDGES = 100
EDGE_PROPERTIES = ("role", "position", "dosage_raw")

# Fixed Cypher; only parameters vary. Edges are ordered by relation, neighbor label, then edge ID.
NEIGHBORS = """
MATCH (c:Entity {build_id:$build,id:$id})-[r:LINK {build_id:$build}]-(n:Entity {build_id:$build})
WHERE $relations IS NULL OR r.relation IN $relations
RETURN r.id AS id, startNode(r).id AS source_id, endNode(r).id AS target_id, r.relation AS relation,
       r.quality_state AS quality_state, r.evidence_ids AS evidence_ids,
       r.role AS role, r.position AS position, r.dosage_raw AS dosage_raw,
       n.id AS n_id, n.label AS n_label, n.type AS n_type
ORDER BY r.relation, n.label, r.id
LIMIT $fetch
"""


def contains_properties(relation, row):
    # A null role or dosage on a CONTAINS edge marks a source conflict, so the keys stay even when null.
    return {k: row[k] for k in EDGE_PROPERTIES} if relation == 'CONTAINS' else {}


def neighborhood(center, relations, build_id=None):
    # The relational side validates the build and the entity, and supplies the true relation totals.
    with services.relational(build_id) as c:
        build = queries.current_build(c)
        entity = queries.require_entity(c, center)
        c.execute('SELECT relation,direction,count FROM v_entity_relation_summary WHERE entity_id=%s '
                  'ORDER BY relation COLLATE "C",direction COLLATE "C"', (center,))
        counts = [dict(row, source='relational') for row in c.fetchall()
                  if not relations or row['relation'] in relations]
    with services.graph() as session:
        marker = session.run("MATCH (p:Projection {build_id:$build,scope:'full',complete:true}) RETURN p",
                             build=build).single()
        found = marker and session.run("MATCH (n:Entity {build_id:$build,id:$id}) RETURN n.label AS label",
                                       build=build, id=center).single()
        if not found:
            raise services.ServiceError("projection_not_ready", "当前批次的图谱尚未构建完成")
        rows = session.run(NEIGHBORS, build=build, id=center, relations=sorted(relations) if relations else None,
                           fetch=MAX_EDGES + 1).data()
    nodes = {center: dict(id=center, label=entity['label'], type=entity['type'])}
    edges, truncated = [], len(rows) > MAX_EDGES
    for row in rows[:MAX_EDGES]:
        if row['n_id'] not in nodes:
            if len(nodes) >= MAX_NODES:
                # Stop at the first edge that would need a 51st node so the result stays an ordered prefix.
                truncated = True
                break
            nodes[row['n_id']] = dict(id=row['n_id'], label=row['n_label'], type=row['n_type'])
        edges.append(dict(id=row['id'], source_id=row['source_id'], target_id=row['target_id'],
                          relation=row['relation'], quality_state=row['quality_state'],
                          evidence_ids=row['evidence_ids'] or [],
                          properties=contains_properties(row['relation'], row)))
    return dict(center=center, nodes=list(nodes.values()), edges=edges, truncated=truncated,
                limits=dict(nodes=MAX_NODES, edges=MAX_EDGES), relation_counts=counts, build_id=build)


# Fixed two-hop templates (spec §6.3). The relational twin is queries.TEMPLATES[name]; tests compare the two.
PATH_TEMPLATES = {
    'herb_patterns_via_formula': dict(
        type='herb',
        match="MATCH (h:Entity {build_id:$build,id:$id})<-[a:LINK {build_id:$build,relation:'CONTAINS'}]-"
              "(f:Entity {build_id:$build})-[b:LINK {build_id:$build,relation:'ASSOCIATED_WITH_PATTERN'}]->"
              "(p:Entity {build_id:$build}) "),
}
PATH_ORDER = "ORDER BY p.label, f.label, p.id, f.id "
PATH_ROWS = (
    "RETURN f.id AS f_id, f.label AS f_label, f.type AS f_type, p.id AS p_id, p.label AS p_label, p.type AS p_type, "
    "a.id AS a_id, a.quality_state AS a_quality, a.evidence_ids AS a_evidence, a.role AS a_role, "
    "a.position AS a_position, a.dosage_raw AS a_dosage_raw, "
    "b.id AS b_id, b.quality_state AS b_quality, b.evidence_ids AS b_evidence ")


def paths(template, entity_id, limit, offset, build_id=None):
    spec = PATH_TEMPLATES[template]
    with services.relational(build_id) as c:
        build = queries.current_build(c)
        entity = queries.require_entity(c, entity_id)
    if entity['type'] != spec['type']:
        raise services.ServiceError('unsupported_entity_type', '该实体类型不适用于所选关系模板')
    with services.graph() as session:
        marker = session.run("MATCH (p:Projection {build_id:$build,scope:'full',complete:true}) RETURN p",
                             build=build).single()
        found = marker and session.run("MATCH (n:Entity {build_id:$build,id:$id}) RETURN n.id", build=build,
                                       id=entity_id).single()
        if not found:
            raise services.ServiceError("projection_not_ready", "当前批次的图谱尚未构建完成")
        total = session.run(spec['match'] + "RETURN count(*) AS total", build=build, id=entity_id).single()['total']
        rows = session.run(spec['match'] + PATH_ROWS + PATH_ORDER + "SKIP $offset LIMIT $limit", build=build,
                           id=entity_id, offset=offset, limit=limit).data()
    nodes, edges, result_paths = {}, {}, []
    for row in rows:
        nodes[entity_id] = queries.node(entity)
        nodes[row['f_id']] = dict(id=row['f_id'], label=row['f_label'], type=row['f_type'])
        nodes[row['p_id']] = dict(id=row['p_id'], label=row['p_label'], type=row['p_type'])
        properties = contains_properties('CONTAINS', {k: row['a_' + k] for k in EDGE_PROPERTIES})
        edges[row['a_id']] = dict(id=row['a_id'], relation='CONTAINS', source_id=row['f_id'], target_id=entity_id,
                                  properties=properties, quality_state=row['a_quality'],
                                  evidence_ids=row['a_evidence'] or [])
        edges[row['b_id']] = dict(id=row['b_id'], relation='ASSOCIATED_WITH_PATTERN', source_id=row['f_id'],
                                  target_id=row['p_id'], properties={}, quality_state=row['b_quality'],
                                  evidence_ids=row['b_evidence'] or [])
        result_paths.append(dict(node_ids=[entity_id, row['f_id'], row['p_id']], edge_ids=[row['a_id'], row['b_id']]))
    return dict(template=template, entity_id=entity_id, paths=result_paths, nodes=nodes, edges=edges,
                note=queries.TWO_HOP_NOTE, total=total, limit=limit, offset=offset, build_id=build)
