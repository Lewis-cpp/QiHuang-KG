"""Graph reads served by the Neo4j full projection (spec §6.2–6.3); Cypher text never contains user input."""

import hashlib

from backend import queries, services

# Fixed type labels written by scripts/project_graph.py; never derived from request data.
TYPE_LABELS = {'herb': 'Herb', 'formula': 'Formula', 'pattern': 'Pattern', 'text': 'Text', 'tcm_term': 'TcmTerm',
               'patent_medicine': 'PatentMedicine', 'herbal_piece': 'HerbalPiece', 'icd11_code': 'Icd11Code',
               'medicinal_property': 'MedicinalProperty'}
# Only display and filter fields live on graph edges; evidence text stays in the relational store.
EDGE_PROPERTIES = ('role', 'position', 'dosage_raw')
LIMITS = dict(nodes=50, edges=100)
NODE_FIELDS = 'id', 'type', 'label', 'category'


def id_digest(node_ids, edge_ids):
    """SHA-256 over both sorted ID sets; Python sorts by code point on both sides of the comparison."""
    text = '\n'.join(['nodes', *sorted(node_ids), 'edges', *sorted(edge_ids)])
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def require_projection(session, build):
    marker = session.run("MATCH (p:Projection {build_id:$build,scope:'full'}) RETURN p.complete AS complete",
                         build=build).single()
    if not marker or marker['complete'] is not True:
        raise services.ServiceError('projection_not_ready', '当前批次的图谱投影尚未完成')


# How many full-projection edges point at a node: formulas containing a herb, patent medicines using a piece,
# formulas linked to a pattern, and so on. A data-coverage count, not a clinical usage frequency.
USAGE = "COUNT { (n)<-[:LINK {build_id:$build,scope:'full'}]-() }"
NODE_MAP = 'n{.id,.type,.label,.category,usage:' + USAGE + '}'


def require_node(session, build, entity_id):
    record = session.run(f'MATCH (n:Entity {{build_id:$build,id:$id}}) RETURN {NODE_MAP} AS node',
                         build=build, id=entity_id).single()
    if record is None:
        raise services.ServiceError('entity_not_found', '当前批次中不存在该实体')
    return record['node']


def graph_edge(edge, source_id, target_id):
    return dict(id=edge['id'], relation=edge['relation'], source_id=source_id, target_id=target_id,
                properties={k: edge[k] for k in EDGE_PROPERTIES if edge.get(k) is not None},
                quality_state=edge['quality_state'], evidence_ids=list(edge['evidence_ids'] or []))


EDGE_MAP = 'r{.id,.relation,.quality_state,.evidence_ids,.role,.position,.dosage_raw}'
ROLE_RANK = {'jun': 0, 'chen': 1, 'zuo': 2, 'shi': 3}  # CONTAINS role; other relations and conflicts rank last
# Per relation type: its total and its first candidates. Python re-sorts them with candidate_key below.
ONE_HOP = ("MATCH (c:Entity {build_id:$build,id:$center}) UNWIND $relations AS relation "
           "CALL (c, relation) { MATCH (c)-[r:LINK {build_id:$build,scope:'full'}]-(:Entity {build_id:$build}) "
           "WHERE r.relation = relation RETURN count(r) AS total } "
           "CALL (c, relation) { MATCH (c)-[r:LINK {build_id:$build,scope:'full'}]-(n:Entity {build_id:$build}) "
           f"WHERE r.relation = relation WITH c, r, n, {USAGE} AS usage "
           "ORDER BY CASE r.role WHEN 'jun' THEN 0 WHEN 'chen' THEN 1 WHEN 'zuo' THEN 2 WHEN 'shi' THEN 3 ELSE 4 END, "
           "usage DESC, n.label, n.id, r.id LIMIT $limit "
           f"RETURN collect({{edge:{EDGE_MAP}, outgoing:startNode(r)=c, "
           "node:n{.id,.type,.label,.category,usage:usage}}) AS rows } "
           "RETURN relation, total, rows")


def candidate_key(row):
    """Within one relation type: CONTAINS role, then the most-pointed-at neighbor, then name in code point order."""
    return (ROLE_RANK.get(row['edge']['role'], len(ROLE_RANK)), -row['node']['usage'], row['node']['label'],
            row['node']['id'], row['edge']['id'])


def neighborhood(center, relations=None, build_id=None):
    """One hop around center, both directions (spec §6.2).

    Smaller relation types come first so a large one cannot crowd them out; the walk stops at the first
    candidate that would exceed a limit, so the result is always a prefix of this order.
    """
    build = services.selected(build_id)['build_id']
    with services.graph() as session:
        require_projection(session, build)
        center_node = require_node(session, build, center)
        groups = session.run(ONE_HOP, build=build, center=center, relations=list(relations or queries.RELATIONS),
                             limit=LIMITS['edges']).data()
    groups = sorted((g for g in groups if g['total']), key=lambda g: (g['total'], g['relation']))
    nodes, edges = {center: center_node}, []
    for row in (row for g in groups for row in sorted(g['rows'], key=candidate_key)):
        neighbor = row['node']
        if len(edges) == LIMITS['edges'] or (neighbor['id'] not in nodes and len(nodes) == LIMITS['nodes']):
            break
        nodes.setdefault(neighbor['id'], neighbor)
        ends = (center, neighbor['id']) if row['outgoing'] else (neighbor['id'], center)
        edges.append(graph_edge(row['edge'], *ends))
    truncated = len(edges) < sum(g['total'] for g in groups)
    # True totals come from the relational store so a truncated canvas can say how much is missing.
    with services.relational(build) as c:
        c.execute('SELECT relation,direction,count FROM v_entity_relation_summary WHERE entity_id=%s '
                  'ORDER BY relation COLLATE "C",direction COLLATE "C"', (center,))
        counts = c.fetchall()
    return dict(center=center, nodes=list(nodes.values()), edges=edges, truncated=truncated, limits=LIMITS,
                relations=list(relations or []), relation_counts=counts,
                relation_counts_source=services.application()['database_engine'], graph_source='neo4j', build_id=build)


# Fixed two-hop Cypher per template; the relational twin lives in queries.TEMPLATES.
PATH_TEMPLATES = {
    'herb_patterns_via_formula': (
        'herb',
        "MATCH (h:Entity {build_id:$build,id:$id})<-[a:LINK {build_id:$build,scope:'full',relation:'CONTAINS'}]-"
        "(f:Entity {build_id:$build})-[b:LINK {build_id:$build,scope:'full',relation:'ASSOCIATED_WITH_PATTERN'}]->"
        "(p:Entity {build_id:$build}) "
        "RETURN a{.id,.relation,.quality_state,.evidence_ids,.role,.position,.dosage_raw} AS a, "
        "b{.id,.relation,.quality_state,.evidence_ids,.role,.position,.dosage_raw} AS b, "
        "f{.id,.type,.label} AS f, p{.id,.type,.label} AS p"),
}


def paths(template, entity_id, limit, offset, build_id=None):
    """Two-hop paths read from Neo4j only, shaped like GET /relation-queries (spec §4.5)."""
    expected, cypher = PATH_TEMPLATES[template]
    build = services.selected(build_id)['build_id']
    with services.graph() as session:
        require_projection(session, build)
        start = require_node(session, build, entity_id)
        if start['type'] != expected:
            raise services.ServiceError('unsupported_entity_type', '该实体类型不适用于所选关系模板')
        rows = session.run(cypher, build=build, id=entity_id).data()
    # Same order as the relational template: pattern label, formula label, then IDs, in code point order.
    rows.sort(key=lambda r: (r['p']['label'], r['f']['label'], r['p']['id'], r['f']['id']))
    result, nodes, edges = [], {}, {}
    for row in rows[offset:offset + limit]:
        nodes[entity_id] = {k: start[k] for k in ('id', 'type', 'label')}
        nodes[row['f']['id']] = row['f']
        nodes[row['p']['id']] = row['p']
        edges[row['a']['id']] = graph_edge(row['a'], row['f']['id'], entity_id)
        edges[row['b']['id']] = graph_edge(row['b'], row['f']['id'], row['p']['id'])
        result.append(dict(node_ids=[entity_id, row['f']['id'], row['p']['id']],
                           edge_ids=[row['a']['id'], row['b']['id']]))
    return dict(template=template, entity_id=entity_id, paths=result, nodes=nodes, edges=edges,
                note=queries.TWO_HOP_NOTE, total=len(rows), limit=limit, offset=offset, build_id=build)
