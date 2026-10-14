"""Project the selected relational release into Neo4j (spec §6.1).

Run after the relational import and setup_services.py:
    .venv/bin/python scripts/project_graph.py            # build, or verify and reuse a complete projection
    .venv/bin/python scripts/project_graph.py --rebuild  # rewrite and re-verify the current batch
    .venv/bin/python scripts/project_graph.py --prune <build_id>  # remove an old batch, never the current one
"""

import argparse
import json
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import graph, services
from backend.queries import EVIDENCE_ORDER
from import_core import require, write_json
from import_vastbase import connection, identify

BATCH = 5000


def relational_rows(db, schema, build):
    """Read the whole release from one snapshot through the import account, without writing."""
    db.set_session(readonly=True, isolation_level="REPEATABLE READ")
    with db.cursor() as c:
        c.execute("SELECT set_config('search_path', %s, true)", (f"{schema}, pg_catalog",))
        c.execute("SELECT id FROM build")
        require([r[0] for r in c.fetchall()] == [build], "Relational build differs from config/app.json")
        c.execute("SELECT id,label,type,category FROM entity ORDER BY id")
        nodes = [dict(zip(("id", "label", "type", "category"), row)) for row in c.fetchall()]
        # Same evidence order as the API, so graph edges list evidence like the detail page does.
        c.execute("SELECT edge_id, array_agg(id ORDER BY " + EVIDENCE_ORDER + ") FROM evidence "
                  "WHERE edge_id IS NOT NULL GROUP BY edge_id")
        evidence = dict(c.fetchall())
        c.execute("SELECT id,source_id,target_id,relation,properties_json,quality_state FROM edge ORDER BY id")
        edges = []
        for id_, source, target, relation, properties, quality in c.fetchall():
            row = dict(id=id_, source_id=source, target_id=target, relation=relation, quality_state=quality,
                       evidence_ids=evidence.get(id_, []))
            values = json.loads(properties)
            if values.get("position_source") == "target_id_order":
                values["position"] = None  # a system-assigned order is not a source claim (spec §5.6)
            row.update({k: values.get(k) for k in graph.EDGE_PROPERTIES} if relation == "CONTAINS"
                       else dict.fromkeys(graph.EDGE_PROPERTIES))
            edges.append(row)
    db.rollback()
    return nodes, edges


def batches(rows):
    for start in range(0, len(rows), BATCH):
        yield rows[start:start + BATCH]


def prepare(session):
    for statement in (
            "CREATE CONSTRAINT entity_identity IF NOT EXISTS FOR (n:Entity) REQUIRE (n.build_id,n.id) IS UNIQUE",
            "CREATE CONSTRAINT projection_identity IF NOT EXISTS FOR (p:Projection) REQUIRE (p.build_id,p.scope) IS UNIQUE",
            "CREATE INDEX link_identity IF NOT EXISTS FOR ()-[r:LINK]-() ON (r.build_id, r.id)",
            "CALL db.awaitIndexes(60)"):
        session.run(statement).consume()


def write(session, build, nodes, edges):
    for kind, label in graph.TYPE_LABELS.items():
        rows = [n for n in nodes if n["type"] == kind]
        # The label comes from the fixed map above, never from data; a bootstrap sample node keeps its scope.
        for chunk in batches(rows):
            session.execute_write(lambda tx: tx.run(
                f"UNWIND $rows AS row MERGE (n:Entity {{build_id:$build,id:row.id}}) SET n:{label}, "
                "n.label=row.label, n.type=row.type, n.category=row.category, n.scope=coalesce(n.scope,'full')",
                rows=chunk, build=build).consume())
    for chunk in batches(edges):
        # Full edges are keyed with scope so the bootstrap sample's relationships stay untouched.
        session.execute_write(lambda tx: tx.run(
            "UNWIND $rows AS row MATCH (s:Entity {build_id:$build,id:row.source_id}) "
            "MATCH (t:Entity {build_id:$build,id:row.target_id}) "
            "MERGE (s)-[r:LINK {build_id:$build,id:row.id,scope:'full'}]->(t) "
            "SET r.relation=row.relation, r.quality_state=row.quality_state, r.evidence_ids=row.evidence_ids, "
            "r.role=row.role, r.position=row.position, r.dosage_raw=row.dosage_raw",
            rows=chunk, build=build).consume())


def verify(session, build, nodes, edges):
    node_ids = session.run("MATCH (n:Entity {build_id:$build}) RETURN n.id AS id", build=build).value("id")
    edge_ids = session.run("MATCH (:Entity {build_id:$build})-[r:LINK {build_id:$build,scope:'full'}]->"
                           "(:Entity {build_id:$build}) RETURN r.id AS id", build=build).value("id")
    expected = graph.id_digest([n["id"] for n in nodes], [e["id"] for e in edges])
    actual = graph.id_digest(node_ids, edge_ids)
    checks = dict(node_count=len(node_ids) == len(nodes), edge_count=len(edge_ids) == len(edges),
                  id_digest=actual == expected)
    return dict(checks=checks, node_count=len(node_ids), edge_count=len(edge_ids),
                relational=dict(node_count=len(nodes), edge_count=len(edges), id_digest=expected), id_digest=actual)


def memory(session):
    try:
        record = session.run("CALL dbms.queryJmx('java.lang:type=Memory') YIELD attributes "
                             "RETURN attributes.HeapMemoryUsage.value.properties AS heap").single()
        return {k: record["heap"][k] for k in ("used", "committed", "max")}
    except Exception:
        return None


def project(rebuild):
    settings = services.application()
    build, engine = settings["build_id"], settings["database_engine"]
    started = time.monotonic()
    with closing(connection(ROOT / f"config/{engine}.json", engine)) as db:
        identify(db, engine)
        nodes, edges = relational_rows(db, settings["schema"], build)
    read_seconds = time.monotonic() - started
    with services.graph() as session:
        prepare(session)
        marker = session.run("MATCH (p:Projection {build_id:$build,scope:'full'}) RETURN p{.*} AS p",
                             build=build).single()
        if marker and marker["p"].get("complete") is True and not rebuild:
            result = verify(session, build, nodes, edges)
            require(all(result["checks"].values()), "Existing projection differs from PostgreSQL; rerun with --rebuild")
            return dict(status="reused", build_id=build, **result, projection=marker["p"], heap=memory(session))
        # Readers get 503 projection_not_ready until verification passes again.
        session.run("MERGE (p:Projection {build_id:$build,scope:'full'}) SET p.complete=false", build=build).consume()
        write_started = time.monotonic()
        write(session, build, nodes, edges)
        write_seconds = time.monotonic() - write_started
        result = verify(session, build, nodes, edges)
        require(all(result["checks"].values()), f"Projection verification failed: {result['checks']}")
        projected_at = datetime.now(timezone.utc).isoformat()
        session.run("MATCH (p:Projection {build_id:$build,scope:'full'}) SET p.complete=true, p.node_count=$nodes, "
                    "p.edge_count=$edges, p.id_digest=$digest, p.projected_at=$at",
                    build=build, nodes=result["node_count"], edges=result["edge_count"], digest=result["id_digest"],
                    at=projected_at).consume()
        heap = memory(session)
    return dict(status="projected", build_id=build, **result, projected_at=projected_at, batch_size=BATCH,
                seconds=dict(read=round(read_seconds, 1), write=round(write_seconds, 1),
                             total=round(time.monotonic() - started, 1)), heap=heap)


def prune(old):
    build = services.application()["build_id"]
    require(old != build, "Refusing to prune the batch selected in config/app.json")
    removed = 0
    with services.graph() as session:
        while True:
            count = session.execute_write(lambda tx: tx.run(
                "MATCH (n:Entity {build_id:$old}) WITH n LIMIT $batch DETACH DELETE n RETURN count(*) AS n",
                old=old, batch=BATCH).single()["n"])
            removed += count
            if not count:
                break
        session.run("MATCH (p:Projection {build_id:$old}) DELETE p", old=old).consume()
    return dict(status="pruned", build_id=old, nodes_removed=removed)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rebuild", action="store_true", help="Rewrite even when a complete projection exists")
    parser.add_argument("--prune", metavar="BUILD_ID", help="Remove every node and edge of an old batch")
    parser.add_argument("--report", type=Path, default=ROOT / "var/graph-projection-report.json")
    args = parser.parse_args()
    report = prune(args.prune) if args.prune else project(args.rebuild)
    report["checked_at"] = datetime.now(timezone.utc).isoformat()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
