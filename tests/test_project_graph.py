"""Projection script against the real Neo4j, on a throw-away build ID; the configured build is only read."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import project_graph
from backend import services

FAKE = "f" * 64


def synthetic():
    nodes = [dict(id=f"x:{kind}:{i}", label=f"{kind}{i}", type=kind) for kind in ("formula", "herb", "pattern") for i in range(3)]
    edges = [dict(id=f"edge:{i}", source_id=f"x:formula:{i}", target_id=f"x:herb:{i}", relation="CONTAINS",
                  quality_state="consistent", evidence_ids=[f"evidence:{i}"], role="jun", position=1, dosage_raw="9g")
             for i in range(3)]
    edges += [dict(id=f"edge:p{i}", source_id=f"x:formula:{i}", target_id=f"x:pattern:{i}", relation="ASSOCIATED_WITH_PATTERN",
                   quality_state="conflicting", evidence_ids=[]) for i in range(3)]
    return nodes, edges


def count(session, build):
    return session.run("MATCH (n:Entity {build_id:$b}) OPTIONAL MATCH (n)-[r:LINK {build_id:$b}]->() "
                       "RETURN count(DISTINCT n) AS n, count(r) AS e", b=build).single().values()


def expect_exit(fn, text):
    try:
        fn()
    except SystemExit as error:
        assert text in str(error), error
    else:
        raise AssertionError(f"expected refusal containing {text!r}")


def main():
    assert set(project_graph.TYPE_LABELS) == set(services.TYPES)
    assert project_graph.digest(["b", "a"]) == project_graph.digest(["a", "b"]) != project_graph.digest(["a"])
    real = services.application()["build_id"]
    nodes, edges = synthetic()
    with services.graph() as session:
        before = count(session, real)
        project_graph.prune(session, FAKE)
        try:
            project_graph.write(session, FAKE, nodes, edges)
            project_graph.write(session, FAKE, nodes, edges)  # MERGE: a rerun adds nothing
            assert count(session, FAKE) == [9, 6]
            marker = session.run("MATCH (p:Projection {build_id:$b,scope:'full'}) RETURN p.complete AS c", b=FAKE).single()
            assert marker["c"] is False, "write() must not mark the projection complete"
            result = project_graph.verify(session, FAKE, nodes, edges)
            assert (result["node_count"], result["edge_count"]) == (9, 6)
            labels = session.run("MATCH (n:Entity:Formula {build_id:$b}) RETURN count(n) AS c", b=FAKE).single()["c"]
            assert labels == 3
            edge = session.run("MATCH ()-[r:LINK {build_id:$b,id:'edge:0'}]->() RETURN r", b=FAKE).single()["r"]
            assert (edge["role"], edge["position"], edge["dosage_raw"], edge["evidence_ids"]) == ("jun", 1, "9g", ["evidence:0"])
            # Verification must catch a missing edge, an extra node and a swapped ID.
            session.run("MATCH ()-[r:LINK {build_id:$b,id:'edge:p0'}]->() DELETE r", b=FAKE).consume()
            expect_exit(lambda: project_graph.verify(session, FAKE, nodes, edges), "edge count")
            project_graph.write(session, FAKE, nodes, edges)
            session.run("CREATE (:Entity {build_id:$b,id:'x:herb:extra',type:'herb',label:'e'})", b=FAKE).consume()
            expect_exit(lambda: project_graph.verify(session, FAKE, nodes, edges), "node count")
            session.run("MATCH (n:Entity {build_id:$b,id:'x:herb:extra'}) DETACH DELETE n", b=FAKE).consume()
            session.run("MATCH (n:Entity {build_id:$b,id:'x:herb:0'}) SET n.id='x:herb:swapped'", b=FAKE).consume()
            expect_exit(lambda: project_graph.verify(session, FAKE, nodes, edges), "digest")
        finally:
            project_graph.prune(session, FAKE)
        assert count(session, FAKE) == [0, 0]
        assert session.run("MATCH (p:Projection {build_id:$b}) RETURN count(p) AS c", b=FAKE).single()["c"] == 0
        expect_exit(lambda: project_graph.prune(session, real), "configured build")
        assert count(session, real) == before, "the configured build must be untouched"
    # The relational side agrees with the stats the API reports.
    build, source_nodes, source_edges = project_graph.read_source("postgresql", ROOT / "config/postgresql.json")
    stats = services.stats()
    assert build == real and (len(source_nodes), len(source_edges)) == (stats["entities"], stats["edges"])
    assert all(e["evidence_ids"] for e in source_edges)
    print("PASS: projection write is idempotent and incomplete until verified; verify rejects a missing edge, an extra node "
          "and a swapped ID; prune clears a build and refuses the configured one; relational read matches stats")


if __name__ == "__main__":
    main()
