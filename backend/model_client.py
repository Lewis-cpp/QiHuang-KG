"""Explicit, bounded OpenAI-compatible model calls for environment verification."""

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from backend.services import ROOT, ServiceError, config

# Caps concurrent billed calls; extra requests fail fast instead of queueing.
SLOTS = threading.BoundedSemaphore(2)
CALL_LOG = ROOT / "var/ai-calls.jsonl"


def settings():
    data = config("model")
    base = str(data.get("base_url", "")).rstrip("/")
    url = urlparse(base)
    local = url.hostname in ("localhost", "127.0.0.1", "::1")
    if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or
            url.query or url.fragment or (url.scheme == "http" and not local)):
        raise ServiceError("invalid_model_config", "模型 API 地址需要 HTTPS，本机服务可使用 HTTP")
    model = data.get("model", "")
    key = os.environ.get(data.get("api_key_env", "QIHUANG_MODEL_API_KEY")) or data.get("api_key")
    if not model or model.startswith("REPLACE") or (not key and not local):
        raise ServiceError("model_not_configured", "模型名称或服务凭据尚未配置")
    timeout = float(data.get("timeout_seconds", 30))
    tokens = int(data.get("max_completion_tokens", 1024))
    if not 1 <= timeout <= 60 or not 32 <= tokens <= 4096:
        raise ServiceError("invalid_model_config", "模型超时或输出上限超出允许范围")
    fingerprint = hashlib.sha256(json.dumps([base, model, key, timeout, tokens]).encode()).hexdigest()
    return dict(base_url=base, model=model, api_key=key, timeout=timeout, tokens=tokens, fingerprint=fingerprint)


def status():
    try:
        selected = settings()
    except ServiceError as error:
        return dict(status="not_configured", code=error.code, message=str(error))
    except (ValueError, TypeError):
        return dict(status="not_configured", message="模型配置格式无效")
    path = ROOT / "var/model-verification.json"
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    verified = saved.get("fingerprint") == selected["fingerprint"] and saved.get("status") == "passed"
    return dict(status="verified" if verified else "not_verified", model=selected["model"],
                checked_at=saved.get("checked_at") if verified else None,
                message="最近一次真实调用通过；健康检查不会调用模型" if verified else "已配置，尚未完成真实调用验证")


def complete_json(system, content, log=None):
    """Return (parsed JSON object, call metadata); `log` adds endpoint/prompt_version/question to the call log."""
    selected = settings()
    payload = dict(model=selected["model"], messages=[dict(role="system", content=system),
                   dict(role="user", content=content)], response_format={"type": "json_object"},
                   max_completion_tokens=selected["tokens"])
    headers = {"Authorization": "Bearer " + selected["api_key"]} if selected["api_key"] else {}
    if not SLOTS.acquire(blocking=False):
        raise ServiceError("model_busy", "模型调用繁忙，请稍后再试")
    entry = {"endpoint": "verify", "prompt_version": None, "question": None, **(log or {})}
    started, data, response, status = time.monotonic(), {}, None, "failed"
    try:
        try:
            client = httpx.Client(timeout=selected["timeout"], follow_redirects=False)
        except ValueError:
            raise ServiceError("model_unavailable", "代理配置无效，请检查 all_proxy 等环境变量") from None
        with client:
            response = client.post(selected["base_url"] + "/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ServiceError("model_incomplete", "模型未返回完整的有效结果")
        result = json.loads(choice["message"]["content"])
        if not isinstance(result, dict):
            raise ValueError()
        status = "ok"
        return result, dict(model=data.get("model", selected["model"]), usage=data.get("usage"),
                            request_id=request_id(data, response))
    except ServiceError as error:
        status = error.code
        raise
    except httpx.HTTPStatusError as error:
        status = "model_http_error"
        raise ServiceError("model_http_error", f"模型服务返回 HTTP {error.response.status_code}") from None
    except httpx.RequestError:
        status = "model_unavailable"
        raise ServiceError("model_unavailable", "模型服务连接失败或超时") from None
    except (KeyError, IndexError, ValueError, TypeError):
        status = "model_invalid_response"
        raise ServiceError("model_invalid_response", "模型响应不符合 JSON 接口约定") from None
    finally:
        SLOTS.release()
        record(dict(entry, request_id=request_id(data, response), model=selected["model"],
                    usage=data.get("usage") if isinstance(data, dict) else None,
                    elapsed_ms=round((time.monotonic() - started) * 1000), status=status))


def request_id(data, response):
    # DeepSeek has no x-request-id header; the completion id identifies the call instead.
    body_id = data.get("id") if isinstance(data, dict) else None
    return body_id or (response.headers.get("x-request-id") if response is not None else None)


def record(entry):
    entry = dict(at=datetime.now(timezone.utc).isoformat(), **entry)
    if entry["question"]:
        entry["question"] = entry["question"][:80]
    try:
        CALL_LOG.parent.mkdir(exist_ok=True)
        with CALL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as error:
        logging.getLogger(__name__).warning("Model call log not written: %s", type(error).__name__)
