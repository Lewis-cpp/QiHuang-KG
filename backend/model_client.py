"""Explicit, bounded OpenAI-compatible model calls for environment verification."""

import hashlib
import json
import os
from urllib.parse import urlparse

import httpx

from backend.services import ROOT, ServiceError, config


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


def complete_json(system, content):
    selected = settings()
    payload = dict(model=selected["model"], messages=[dict(role="system", content=system),
                   dict(role="user", content=content)], response_format={"type": "json_object"},
                   max_completion_tokens=selected["tokens"])
    headers = {"Authorization": "Bearer " + selected["api_key"]} if selected["api_key"] else {}
    try:
        with httpx.Client(timeout=selected["timeout"], follow_redirects=False) as client:
            response = client.post(selected["base_url"] + "/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ServiceError("model_incomplete", "模型未返回完整的有效结果")
        result = json.loads(choice["message"]["content"])
        if not isinstance(result, dict):
            raise ValueError()
        return result, dict(model=data.get("model", selected["model"]), usage=data.get("usage"),
                            request_id=response.headers.get("x-request-id"))
    except httpx.HTTPStatusError as error:
        raise ServiceError("model_http_error", f"模型服务返回 HTTP {error.response.status_code}") from None
    except httpx.RequestError:
        raise ServiceError("model_unavailable", "模型服务连接失败或超时") from None
    except (KeyError, IndexError, ValueError, TypeError):
        raise ServiceError("model_invalid_response", "模型响应不符合 JSON 接口约定") from None
