"""Verify actual services; --check-model makes two bounded, potentially billed model calls."""

import argparse
import hashlib
import json
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import model_client, services
from import_core import canonical, require, write_json
from import_vastbase import connection, identify, probe


def check_postgres():
    engine = services.application()["database_engine"]
    with closing(connection(ROOT / f"config/{engine}.json", engine)) as db:
        identity = identify(db, engine)
        checks = probe(db)
    return dict(status="passed", **identity, probe=checks, data=services.stats())


def check_neo4j():
    from neo4j.exceptions import ConstraintError
    data = services.sample_source()
    build = data["build_id"]
    with services.graph() as session:
        session.run("CREATE CONSTRAINT entity_identity IF NOT EXISTS FOR (n:Entity) "
                    "REQUIRE (n.build_id,n.id) IS UNIQUE").consume()
        session.run("CREATE CONSTRAINT projection_identity IF NOT EXISTS FOR (p:Projection) "
                    "REQUIRE (p.build_id,p.scope) IS UNIQUE").consume()
        session.run("CALL db.awaitIndexes(30)").consume()
        with session.begin_transaction(timeout=15) as tx:
            tx.run("UNWIND $rows AS row MERGE (n:Entity {build_id:$build,id:row.id}) "
                   "SET n.label=row.label,n.type=row.type,n.scope='bootstrap'", rows=data["nodes"], build=build).consume()
            tx.run("UNWIND $rows AS row MATCH (s:Entity {build_id:$build,id:row.source_id}),"
                   "(t:Entity {build_id:$build,id:row.target_id}) "
                   "MERGE (s)-[r:LINK {build_id:$build,id:row.id}]->(t) "
                   "SET r.relation=row.relation,r.evidence_ids=row.evidence_ids,r.scope='bootstrap'",
                   rows=data["edges"], build=build).consume()
            nodes = tx.run("MATCH (n:Entity {build_id:$build,scope:'bootstrap'}) "
                           "RETURN n.id AS id,n.label AS label,n.type AS type ORDER BY id", build=build).data()
            edges = tx.run("MATCH (s:Entity {build_id:$build})-[r:LINK {build_id:$build,scope:'bootstrap'}]->(t:Entity) "
                           "RETURN r.id AS id,s.id AS source_id,r.relation AS relation,t.id AS target_id," 
                           "r.evidence_ids AS evidence_ids ORDER BY id", build=build).data()
            require(nodes == data["nodes"] and edges == data["edges"], "Graph sample differs from PostgreSQL")
            tx.run("MERGE (p:Projection {build_id:$build,scope:'bootstrap'}) "
                   "SET p.complete=true,p.node_count=$nodes,p.edge_count=$edges,p.source_sha256=$sha",
                   build=build, nodes=len(nodes), edges=len(edges),
                   sha=hashlib.sha256(canonical(data).encode()).hexdigest()).consume()
            tx.commit()
        # The duplicate must be rejected by the actual unique constraint.
        try:
            with session.begin_transaction() as tx:
                tx.run("CREATE (:Entity {build_id:$build,id:$id})", build=build,
                       id=data["nodes"][0]["id"]).consume()
                tx.rollback()
        except ConstraintError:
            pass
        else:
            raise ValueError("Neo4j unique constraint did not reject a duplicate")
        marker = uuid.uuid4().hex
        with session.begin_transaction() as tx:
            tx.run("CREATE (:EnvironmentProbe {id:$id})", id=marker).consume()
            tx.rollback()
        require(session.run("MATCH (n:EnvironmentProbe {id:$id}) RETURN count(n) AS count", id=marker).single()["count"] == 0,
                "Neo4j transaction rollback failed")
        one_hop = session.run("MATCH (:Entity {build_id:$build,id:$formula})-[r:LINK]->(:Entity {build_id:$build}) "
                              "WHERE r.relation=$relation RETURN count(r) AS count", build=build,
                              formula=services.SAMPLE_FORMULA, relation="CONTAINS").single()["count"]
        two_hop = session.run("MATCH (:Entity {build_id:$build,id:$herb})<-[a:LINK]-(f:Entity {build_id:$build})"
                              "-[b:LINK]->(:Entity {build_id:$build,id:$pattern}) "
                              "WHERE a.relation=$contains AND b.relation=$associated RETURN count(f) AS count",
                              build=build, herb="bencaodian:herb:ren_shen", pattern="bencaodian:pattern:pi_qi_xu",
                              contains="CONTAINS", associated="ASSOCIATED_WITH_PATTERN").single()["count"]
        require(one_hop == 4 and two_hop == 1, "Neo4j one/two-hop query mismatch")
        plan = session.run("EXPLAIN MATCH (n:Entity {build_id:$build,id:$id}) RETURN n",
                           build=build, id=services.SAMPLE_FORMULA).consume().plan
        require("Index" in str(plan), "Neo4j plan does not use the identity index")
    return dict(status="passed", server=services.graph_health(), scope="bootstrap", build_id=build,
                nodes=len(nodes), edges=len(edges), one_hop=one_hop, two_hop=two_hop,
                checks=["connectivity", "unique_constraint", "index_plan", "rollback", "parameterized_one_hop",
                        "parameterized_two_hop", "source_content_equality"], plan=str(plan))


def check_model():
    selected = model_client.settings()
    query, qmeta = model_client.complete_json(
        '将检索问题转换为 JSON，只允许 q 和 type 两个字符串字段；type 为 formula。不得返回 SQL。',
        '查找方剂“四君子汤”。')
    require(query == {"q": "四君子汤", "type": "formula"}, "Model query structure or values did not match")
    with services.relational() as c:
        c.execute("SELECT h.label,e.properties_json,v.id AS evidence_id FROM edge e JOIN entity h ON h.id=e.target_id "
                  "JOIN evidence v ON v.edge_id=e.id WHERE e.source_id=%s AND e.relation='CONTAINS' ORDER BY e.id,v.id",
                  (services.SAMPLE_FORMULA,))
        materials = [dict(herb=r["label"], dosage=json.loads(r["properties_json"])["dosage_raw"],
                          evidence_id=r["evidence_id"]) for r in c.fetchall()]
    explanation, emeta = model_client.complete_json(
        '你是资料整理助手。仅根据提供材料，用中文解释四君子汤的组成，不增加适应证或用药建议。'
        '返回 JSON，恰好包含 explanation 非空字符串与 evidence_ids 非空字符串数组，引用只能来自材料。',
        canonical(materials))
    require(set(explanation) == {"explanation", "evidence_ids"} and isinstance(explanation["explanation"], str)
            and explanation["explanation"].strip(), "Model explanation schema mismatch")
    citations = explanation["evidence_ids"]
    require(isinstance(citations, list) and citations and all(isinstance(x, str) for x in citations), "Invalid citations")
    require(set(citations) <= {r["evidence_id"] for r in materials}, "Model fabricated evidence IDs")
    require(all(name in explanation["explanation"] for name in ("人参", "白术", "茯苓", "甘草")),
            "Model omitted a source herb")
    return dict(status="passed", fingerprint=selected["fingerprint"], checked_at=datetime.now(timezone.utc).isoformat(),
                model=selected["model"], query=query, explanation=explanation, calls=[qmeta, emeta],
                scope="connection_and_contract_smoke_test_not_full_AI_acceptance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-model", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / "var/environment-report.json")
    args = parser.parse_args()
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), services={})
    for name, fn in (("postgresql", check_postgres), ("neo4j", check_neo4j)):
        try:
            report["services"][name] = fn()
        except Exception as error:
            report["services"][name] = dict(status="failed", error=str(error) if isinstance(error, services.ServiceError)
                                            else type(error).__name__)
    if args.check_model:
        try:
            report["services"]["model"] = check_model()
        except Exception as error:
            report["services"]["model"] = dict(status="blocked" if isinstance(error, services.ServiceError)
                and error.code.endswith("not_configured") else "failed",
                error=str(error) if isinstance(error, services.ServiceError) else type(error).__name__)
        write_json(ROOT / "var/model-verification.json", report["services"]["model"])
    else:
        report["services"]["model"] = model_client.status()
    passed = all(r["status"] in ("passed", "verified") for r in report["services"].values())
    report["status"] = "passed" if passed else "incomplete"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
