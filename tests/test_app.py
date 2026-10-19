"""Run after setup_services and verify_environment with .venv/bin/python tests/test_app.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import app
from backend import model_client, services


def model_contract_checks():
    selected = dict(base_url="https://model.example.invalid/v1", model="test-model", api_key="private-test-value",
                    timeout=2, tokens=64, fingerprint="test")
    real_client = httpx.Client
    def handler(request):
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["max_completion_tokens"] == 64
        assert request.headers["Authorization"] == "Bearer private-test-value"
        return httpx.Response(200, json={"model": "test-model", "choices": [{"finish_reason": "stop",
                              "message": {"content": '{"q":"四君子汤"}'}}]})
    with patch.object(model_client, "settings", return_value=selected):
        with patch.object(model_client.httpx, "Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            result, meta = model_client.complete_json("Return JSON", "query")
            assert result == {"q": "四君子汤"} and meta["model"] == "test-model"
        for response, code in (
                (httpx.Response(429, json={"error": "private-test-value"}), "model_http_error"),
                (httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}), "model_incomplete"),
                (httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]}), "model_invalid_response")):
            with patch.object(model_client.httpx, "Client", side_effect=lambda **kw: real_client(
                    transport=httpx.MockTransport(lambda request: response), **kw)):
                try:
                    model_client.complete_json("Return JSON", "query")
                except services.ServiceError as error:
                    assert error.code == code and "private-test-value" not in str(error)
                else:
                    raise AssertionError("Invalid model response accepted")


def main():
    client = TestClient(app)
    assert client.get("/api/v1/health/live").json() == {"status": "alive"}
    with patch.object(model_client, "complete_json", side_effect=AssertionError("Health check must not call model")):
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["services"]["database"]["status"] == "ready"
        assert health.json()["services"]["neo4j"]["projection"] in ("sample", "full")
    stats = client.get("/api/v1/stats").json()
    assert (stats["entities"], stats["edges"], stats["evidence"], stats["business_records"]) == (20374, 179502, 291308, 199876)
    result = client.get("/api/v1/entities", params={"q": "四君子汤", "type": "formula"}).json()
    assert result["total"] == 1 and result["items"][0]["id"] == services.SAMPLE_FORMULA
    assert client.get("/api/v1/entities", params={"q": "' OR 1=1 --"}).json()["total"] == 0
    assert client.get("/api/v1/entities", params={"q": "%"}).json()["total"] < 100
    for params in ({"limit": 51}, {"offset": -1}, {"q": "x" * 101}, {"type": "invalid"}):
        assert client.get("/api/v1/entities", params=params).status_code == 422
    graph = client.get("/api/v1/graph/sample").json()
    assert graph["build_id"] == stats["build_id"] and len(graph["nodes"]) == 6 and len(graph["edges"]) == 5
    assert all(e["evidence_ids"] for e in graph["edges"])
    # One-hop graph: same edge set as the relational store, endpoints inside the node set, hard limits on hubs.
    one_hop = client.get("/api/v1/graph", params={"center": services.SAMPLE_FORMULA}).json()
    assert one_hop["build_id"] == stats["build_id"] and not one_hop["truncated"]
    expected = sum(c["count"] for c in one_hop["relation_counts"])
    assert len(one_hop["edges"]) == expected == 6 and len(one_hop["nodes"]) == 7
    node_ids = {n["id"] for n in one_hop["nodes"]}
    assert all(e["source_id"] in node_ids and e["target_id"] in node_ids and e["evidence_ids"] for e in one_hop["edges"])
    for relation in ("CONTAINS", "ASSOCIATED_WITH_PATTERN"):
        listed = client.get(f"/api/v1/entities/{services.SAMPLE_FORMULA}/relations",
                            params={"relation": relation, "direction": "out", "limit": 50}).json()
        assert {i["edge"]["id"] for i in listed["items"]} == {e["id"] for e in one_hop["edges"] if e["relation"] == relation}
    filtered = client.get("/api/v1/graph", params={"center": services.SAMPLE_FORMULA, "relation": "CONTAINS"}).json()
    assert {e["relation"] for e in filtered["edges"]} == {"CONTAINS"} and len(filtered["edges"]) == 4
    assert all(set(e["properties"]) <= {"role", "position", "dosage_raw"} for e in filtered["edges"])
    hub = "tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842"
    big = client.get("/api/v1/graph", params={"center": hub}).json()
    assert big["truncated"] and len(big["nodes"]) <= 50 and len(big["edges"]) <= 100
    assert big["relation_counts"][0]["count"] > len(big["edges"])
    assert client.get("/api/v1/graph", params={"center": "bencaodian:formula:none"}).status_code == 404
    assert client.get("/api/v1/graph", params={"center": hub, "relation": "X"}).status_code == 422
    assert client.get("/api/v1/graph", params={"center": hub, "build_id": "0" * 64}).status_code == 409
    with patch.object(services, "graph", side_effect=services.ServiceError("neo4j_unavailable", "图数据库暂时不可用")):
        down = client.get("/api/v1/graph", params={"center": services.SAMPLE_FORMULA})
        assert down.status_code == 503 and down.json()["error"]["code"] == "neo4j_unavailable"
        assert client.get(f"/api/v1/entities/{services.SAMPLE_FORMULA}").status_code == 200
    # Two-hop paths: Neo4j and PostgreSQL must return the same result set (double-store consistency evidence).
    # The graph keeps only display properties on edges, so compare those three keys.
    def shown(page):
        for edge in page["edges"].values():
            edge["properties"] = {k: v for k, v in edge["properties"].items() if k in ("role", "position", "dosage_raw")}
        return page
    with services.relational() as cursor:
        cursor.execute("SELECT id FROM entity WHERE type='herb' AND dataset_id='bencaodian' ORDER BY id")
        herbs = [row["id"] for row in cursor.fetchall()]
    compared = with_paths = 0
    for herb in herbs:
        query = {"template": "herb_patterns_via_formula", "entity_id": herb, "limit": 50}
        from_graph = client.get("/api/v1/graph/paths", params=query).json()
        from_database = shown(client.get("/api/v1/relation-queries", params=query).json())
        assert from_graph == from_database, herb
        compared += 1
        with_paths += from_graph["total"] > 0
    assert compared == len(herbs) and with_paths > 10
    gan_cao = {"template": "herb_patterns_via_formula", "entity_id": "bencaodian:herb:gan_cao"}
    first, second = (client.get("/api/v1/graph/paths", params=gan_cao | {"limit": 5, "offset": o}).json() for o in (0, 5))
    whole = client.get("/api/v1/graph/paths", params=gan_cao | {"limit": 10}).json()
    assert first["total"] > 10 and first["paths"] + second["paths"] == whole["paths"] and first["note"]
    assert client.get("/api/v1/graph/paths", params=gan_cao | {"limit": 51}).status_code == 422
    assert client.get("/api/v1/graph/paths", params=gan_cao | {"template": "x"}).status_code == 422
    assert client.get("/api/v1/graph/paths", params=gan_cao | {"entity_id": services.SAMPLE_FORMULA}).status_code == 422
    assert client.get("/api/v1/graph/paths", params=gan_cao | {"entity_id": "bencaodian:herb:none"}).status_code == 404
    assert client.get("/api/v1/graph/paths", params=gan_cao | {"build_id": "0" * 64}).status_code == 409
    with patch.object(services, "graph", side_effect=services.ServiceError("neo4j_unavailable", "图数据库暂时不可用")):
        assert client.get("/api/v1/graph/paths", params=gan_cao).status_code == 503
    config = services.application()
    with patch.object(services, "application", return_value={**config, "build_id": "0" * 64}):
        assert client.get("/api/v1/graph/sample").status_code == 503
        assert client.get("/api/v1/stats").status_code == 503
    with patch.object(services, "graph_health", side_effect=services.ServiceError("neo4j_unavailable", "图库不可用")):
        degraded = client.get("/api/v1/health")
        assert degraded.status_code == 200 and degraded.json()["status"] == "degraded"
        assert client.get("/api/v1/stats").status_code == 200
    with patch.object(services, "database_health", side_effect=services.ServiceError("database_unavailable", "主库不可用")):
        assert client.get("/api/v1/health").status_code == 503
    try:
        with services.relational() as c:
            c.execute("UPDATE entity SET label=label WHERE false")
    except services.ServiceError as error:
        assert error.code == "database_unavailable"
    else:
        raise AssertionError("Application connection allowed writes")
    model_contract_checks()
    print("PASS: actual database API, limits, SQL binding/LIKE escaping, graph batch, read-only transaction, "
          "failure isolation, no billed health checks, mocked model contract/error redaction (not a real model call)")


if __name__ == "__main__":
    main()
