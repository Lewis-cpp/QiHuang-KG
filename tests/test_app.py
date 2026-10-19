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
        assert health.json()["services"]["neo4j"]["projection"] == "sample"
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
