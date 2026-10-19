#!/usr/bin/env python3
"""Project the configured relational build into Neo4j (spec §6.1).

Reads the build with the import account in a read-only transaction, writes nodes, then edges, then verifies counts
and ID digests against the relational side. The Projection marker only becomes complete after verification passes.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import queries, services  # noqa: E402
from import_vastbase import connection  # noqa: E402

BATCH = 5000
# Fixed mapping; labels are never built from user input.
TYPE_LABELS = {
    "herb": "Herb", "formula": "Formula", "pattern": "Pattern", "text": "Text", "tcm_term": "TcmTerm",
    "patent_medicine": "PatentMedicine", "herbal_piece": "HerbalPiece", "icd11_code": "Icd11Code",
    "medicinal_property": "MedicinalProperty",
}
CONTAINS_KEYS = ("role", "position", "dosage_raw")


def require(condition, message):
    if not condition:
        raise SystemExit(f"error: {message}")


def digest(ids):
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def batches(rows):
    for start in range(0, len(rows), BATCH):
        yield rows[start:start + BATCH]


def read_source(engine, config):
    app = services.application()
    require(app["database_engine"] == engine, "app.json database_engine differs from --engine")
    db = connection(config, engine)
    try:
        db.set_session(readonly=True)
        with db.cursor() as c:
            c.execute("SET LOCAL search_path TO " + '"' + app["schema"] + '", pg_catalog')
            c.execute("SELECT id FROM build")
            builds = [r[0] for r in c.fetchall()]
            require(builds == [app["build_id"]], "relational build differs from config/app.json")
            c.execute("SELECT id,label,type FROM entity ORDER BY id")
            nodes = [dict(id=i, label=label, type=t) for i, label, t in c.fetchall()]
            unknown = {n["type"] for n in nodes} - TYPE_LABELS.keys()
            require(not unknown, f"entity types without a graph label: {sorted(unknown)}")
            # Same evidence order as the relational API, so both stores return identical lists.
            c.execute("SELECT edge_id,id FROM evidence WHERE edge_id IS NOT NULL ORDER BY edge_id, " + queries.EVIDENCE_ORDER)
            evidence = {}
            for edge_id, evidence_id in c.fetchall():
                evidence.setdefault(edge_id, []).append(evidence_id)
            c.execute("SELECT id,source_id,relation,target_id,quality_state,properties_json FROM edge ORDER BY id")
            edges = []
            for i, s, relation, t, quality, props in c.fetchall():
                props = json.loads(props)
                edge = dict(id=i, source_id=s, target_id=t, relation=relation, quality_state=quality,
                            evidence_ids=evidence.get(i, []))
                if relation == "CONTAINS":
                    edge.update({k: props.get(k) for k in CONTAINS_KEYS})
                edges.append(edge)
    finally:
        db.close()
    return app["build_id"], nodes, edges


def write(session, build, nodes, edges):
    session.run("CREATE CONSTRAINT entity_identity IF NOT EXISTS FOR (n:Entity) "
                "REQUIRE (n.build_id,n.id) IS UNIQUE").consume()
    session.run("CREATE CONSTRAINT projection_identity IF NOT EXISTS FOR (p:Projection) "
                "REQUIRE (p.build_id,p.scope) IS UNIQUE").consume()
    session.run("CREATE INDEX link_identity IF NOT EXISTS FOR ()-[r:LINK]-() ON (r.build_id,r.id)").consume()
    session.run("CALL db.awaitIndexes(60)").consume()
    # A rerun invalidates the marker until verification passes again.
    session.run("MERGE (p:Projection {build_id:$build,scope:'full'}) SET p.complete=false", build=build).consume()
    # Labels need static Cypher, so write one pass per type.
    for kind, label in TYPE_LABELS.items():
        rows = [n for n in nodes if n["type"] == kind]
        for chunk in batches(rows):
            session.run(f"UNWIND $rows AS row MERGE (n:Entity {{build_id:$build,id:row.id}}) "
                        f"SET n:{label},n.label=row.label,n.type=row.type,n.scope='full'",
                        rows=chunk, build=build).consume()
    for chunk in batches(edges):
        session.run("UNWIND $rows AS row MATCH (s:Entity {build_id:$build,id:row.source_id}),"
                    "(t:Entity {build_id:$build,id:row.target_id}) "
                    "MERGE (s)-[r:LINK {build_id:$build,id:row.id}]->(t) "
                    "SET r.relation=row.relation,r.evidence_ids=row.evidence_ids,r.quality_state=row.quality_state,"
                    "r.role=row.role,r.position=row.position,r.dosage_raw=row.dosage_raw,r.scope='full'",
                    rows=[dict(e, role=e.get("role"), position=e.get("position"), dosage_raw=e.get("dosage_raw"))
                          for e in chunk], build=build).consume()


def verify(session, build, nodes, edges):
    graph_nodes = [r["id"] for r in session.run("MATCH (n:Entity {build_id:$build}) RETURN n.id AS id", build=build)]
    graph_edges = [r["id"] for r in session.run(
        "MATCH (:Entity {build_id:$build})-[r:LINK {build_id:$build}]->(:Entity {build_id:$build}) "
        "RETURN r.id AS id", build=build)]
    source_nodes, source_edges = digest(n["id"] for n in nodes), digest(e["id"] for e in edges)
    require(len(graph_nodes) == len(nodes), f"node count {len(graph_nodes)} != {len(nodes)}")
    require(len(graph_edges) == len(edges), f"edge count {len(graph_edges)} != {len(edges)}")
    require(digest(graph_nodes) == source_nodes, "node ID digest differs from the relational build")
    require(digest(graph_edges) == source_edges, "edge ID digest differs from the relational build")
    # Spot check the label mapping: every node carries exactly the label for its type.
    for kind, label in TYPE_LABELS.items():
        expected = sum(1 for n in nodes if n["type"] == kind)
        actual = session.run(f"MATCH (n:Entity:{label} {{build_id:$build,type:$kind}}) RETURN count(n) AS c",
                             build=build, kind=kind).single()["c"]
        require(actual == expected, f"label {label}: {actual} != {expected}")
    return dict(node_count=len(nodes), edge_count=len(edges), id_digest=dict(nodes=source_nodes, edges=source_edges))


def prune(session, build):
    require(build != services.application()["build_id"], "refusing to prune the configured build")
    for _ in range(1000):
        removed = session.run("MATCH (n:Entity {build_id:$build}) WITH n LIMIT 5000 DETACH DELETE n "
                              "RETURN count(*) AS c", build=build).single()["c"]
        if not removed:
            break
    session.run("MATCH (p:Projection {build_id:$build}) DELETE p", build=build).consume()
    return dict(pruned=build)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("vastbase", "postgresql"), default="postgresql")
    parser.add_argument("--config", type=Path, help="Default: config/<engine>.json")
    parser.add_argument("--prune", metavar="BUILD_ID", help="Delete another build's projection and exit")
    parser.add_argument("--report", type=Path, default=ROOT / "var/graph-projection-report.json")
    args = parser.parse_args()
    if args.prune:
        with services.graph() as session:
            print(json.dumps(prune(session, args.prune)))
        return
    started = time.monotonic()
    build, nodes, edges = read_source(args.engine, args.config or ROOT / f"config/{args.engine}.json")
    read_seconds = time.monotonic() - started
    with services.graph() as session:
        write(session, build, nodes, edges)
        written = time.monotonic() - started
        result = verify(session, build, nodes, edges)
        session.run("MATCH (p:Projection {build_id:$build,scope:'full'}) SET p.complete=true,p.node_count=$n,"
                    "p.edge_count=$e,p.id_digest=$d,p.completed_at=datetime()", build=build,
                    n=result["node_count"], e=result["edge_count"],
                    d=result["id_digest"]["nodes"] + ":" + result["id_digest"]["edges"]).consume()
    report = dict(build_id=build, engine=args.engine, scope="full", **result,
                  seconds=dict(read=round(read_seconds, 1), write=round(written - read_seconds, 1),
                               total=round(time.monotonic() - started, 1)))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
