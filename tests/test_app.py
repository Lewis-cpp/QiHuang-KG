"""Run after setup_services and verify_environment with .venv/bin/python tests/test_app.py."""

import json
import sys
import tempfile
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
    with tempfile.TemporaryDirectory() as tmp, patch.object(model_client, "settings", return_value=selected), \
            patch.object(model_client, "CALL_LOG", Path(tmp) / "ai-calls.jsonl"):
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
        with patch.object(model_client.httpx, "Client", side_effect=ValueError("Unknown scheme for proxy URL")):
            try:
                model_client.complete_json("Return JSON", "query")
            except services.ServiceError as error:
                assert error.code == "model_unavailable" and "代理" in str(error)
            else:
                raise AssertionError("Invalid proxy setting not reported")
        held = [model_client.SLOTS.acquire(blocking=False) for _ in range(2)]
        try:
            try:
                model_client.complete_json("Return JSON", "query")
            except services.ServiceError as error:
                assert error.code == "model_busy"
            else:
                raise AssertionError("Third concurrent model call allowed")
        finally:
            for ok in held:
                ok and model_client.SLOTS.release()
    assert services.ERROR_STATUS["model_http_error"] == 502 and "model_busy" not in services.ERROR_STATUS


def model_log_checks():
    selected = dict(base_url="https://model.example.invalid/v1", model="test-model", api_key="private-test-value",
                    timeout=2, tokens=64, fingerprint="test")
    real_client = httpx.Client
    response = httpx.Response(200, json={"id": "call-1", "usage": {"total_tokens": 9}, "choices": [
        {"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]})
    with tempfile.TemporaryDirectory() as tmp, patch.object(model_client, "settings", return_value=selected), \
            patch.object(model_client, "CALL_LOG", Path(tmp) / "ai-calls.jsonl"), \
            patch.object(model_client.httpx, "Client", side_effect=lambda **kw: real_client(
                transport=httpx.MockTransport(lambda request: response), **kw)):
        _, meta = model_client.complete_json("Return JSON", "query", log=dict(
            endpoint="query", prompt_version="query_v1", question="问" * 100))
        assert meta["request_id"] == "call-1"
        with patch.object(model_client.httpx, "Client", side_effect=ValueError("proxy")):
            try:
                model_client.complete_json("Return JSON", "query")
            except services.ServiceError:
                pass
        text = (Path(tmp) / "ai-calls.jsonl").read_text()
        assert "private-test-value" not in text
        ok, failed = [json.loads(line) for line in text.splitlines()]
        assert (ok["endpoint"], ok["prompt_version"], ok["status"], ok["request_id"]) == ("query", "query_v1", "ok", "call-1")
        assert ok["question"] == "问" * 80 and ok["usage"] == {"total_tokens": 9} and ok["elapsed_ms"] >= 0
        assert (failed["endpoint"], failed["status"]) == ("verify", "model_unavailable")
    assert model_client.SLOTS.acquire(blocking=False) and model_client.SLOTS.acquire(blocking=False)
    model_client.SLOTS.release(); model_client.SLOTS.release()


def main():
    client = TestClient(app)
    assert client.get("/api/v1/health/live").json() == {"status": "alive"}
    with patch.object(model_client, "complete_json", side_effect=AssertionError("Health check must not call model")):
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["services"]["database"]["status"] == "ready"
        assert health.json()["services"]["neo4j"]["projection"] == "full"
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
    model_log_checks()
    print("PASS: actual database API, limits, SQL binding/LIKE escaping, graph batch, read-only transaction, "
          "failure isolation, no billed health checks, mocked model contract/error redaction (not a real model call)")


if __name__ == "__main__":
    main()
