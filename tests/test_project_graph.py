"""Projection script against the real Neo4j, on a throw-away build ID; the configured build is only read."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import project_graph
from neo4j import GraphDatabase
from backend import graph, services

FAKE = "f" * 64


def synthetic():
    nodes = [dict(id=f"x:{kind}:{i}", label=f"{kind}{i}", type=kind, category=None)
             for kind in ("formula", "herb", "pattern") for i in range(3)]
    none = dict(role=None, position=None, dosage_raw=None)
    edges = [dict(id=f"edge:{i}", source_id=f"x:formula:{i}", target_id=f"x:herb:{i}", relation="CONTAINS",
                  quality_state="consistent", evidence_ids=[f"evidence:{i}"], role="jun", position=1, dosage_raw="9g")
             for i in range(3)]
    edges += [dict(id=f"edge:p{i}", source_id=f"x:formula:{i}", target_id=f"x:pattern:{i}", relation="ASSOCIATED_WITH_PATTERN",
                   quality_state="conflicting", evidence_ids=[], **none) for i in range(3)]
    return nodes, edges


def count(session, build):
    return session.run("MATCH (n:Entity {build_id:$b}) OPTIONAL MATCH (n)-[r:LINK {build_id:$b}]->() "
                       "RETURN count(DISTINCT n) AS n, count(r) AS e", b=build).single().values()


def expect_exit(fn, text):
    try:
        fn()
    except ValueError as error:
        assert text in str(error), error
    else:
        raise AssertionError(f"expected refusal containing {text!r}")


def failed(result):
    return sorted(name for name, ok in result["checks"].items() if not ok)


def main():
    assert set(graph.TYPE_LABELS) == set(services.TYPES)
    assert graph.id_digest(["b", "a"], ["e"]) == graph.id_digest(["a", "b"], ["e"]) != graph.id_digest(["a"], ["e"])
    real = services.application()["build_id"]
    nodes, edges = synthetic()
    settings = services.config("neo4j")
    # A raw driver: services.graph() would report any failure in the block as "Neo4j unavailable".
    with GraphDatabase.driver(settings["uri"], auth=(settings["user"], settings["password"])) as driver, \
            driver.session(database=settings.get("database", "neo4j")) as session:
        before = count(session, real)
        project_graph.prepare(session)
        project_graph.prune(FAKE)
        try:
            project_graph.write(session, FAKE, nodes, edges)
            project_graph.write(session, FAKE, nodes, edges)  # MERGE: a rerun adds nothing
            assert count(session, FAKE) == [9, 6]
            assert session.run("MATCH (p:Projection {build_id:$b}) RETURN count(p) AS c", b=FAKE).single()["c"] == 0, \
                "write() must not create a completion marker"
            ok = project_graph.verify(session, FAKE, nodes, edges)
            assert failed(ok) == [] and (ok["node_count"], ok["edge_count"]) == (9, 6)
            formulas = session.run("MATCH (n:Entity:Formula {build_id:$b}) RETURN count(n) AS c", b=FAKE).single()["c"]
            assert formulas == 3
            edge = session.run("MATCH ()-[r:LINK {build_id:$b,id:'edge:0'}]->() RETURN r", b=FAKE).single()["r"]
            assert (edge["role"], edge["position"], edge["dosage_raw"], edge["evidence_ids"]) == ("jun", 1, "9g", ["evidence:0"])
            # Verification must catch a missing edge, an extra node and a swapped ID.
            session.run("MATCH ()-[r:LINK {build_id:$b,id:'edge:p0'}]->() DELETE r", b=FAKE).consume()
            assert failed(project_graph.verify(session, FAKE, nodes, edges)) == ["edge_count", "id_digest"]
            project_graph.write(session, FAKE, nodes, edges)
            session.run("CREATE (:Entity {build_id:$b,id:'x:herb:extra',type:'herb',label:'e'})", b=FAKE).consume()
            assert failed(project_graph.verify(session, FAKE, nodes, edges)) == ["id_digest", "node_count"]
            session.run("MATCH (n:Entity {build_id:$b,id:'x:herb:extra'}) DETACH DELETE n", b=FAKE).consume()
            session.run("MATCH (n:Entity {build_id:$b,id:'x:herb:0'}) SET n.id='x:herb:swapped'", b=FAKE).consume()
            assert failed(project_graph.verify(session, FAKE, nodes, edges)) == ["id_digest"]
        finally:
            removed = project_graph.prune(FAKE)
        assert removed["nodes_removed"] >= 9
        assert count(session, FAKE) == [0, 0]
        expect_exit(lambda: project_graph.prune(real), "Refusing to prune")
        assert count(session, real) == before, "the configured build must be untouched"
    print("PASS: projection write is idempotent and creates no completion marker; verify flags a missing edge, an extra "
          "node and a swapped ID; prune clears a build and refuses the configured one")


if __name__ == "__main__":
    main()
