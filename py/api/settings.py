"""设置 API 路由 - 全局配置读写"""

from __future__ import annotations

import time
from typing import Any

import requests
from fastapi import APIRouter, HTTPException

from ..services.config_service import config_service
from ..shared.http_client import create_session, request_local_retry

router = APIRouter()


def _models_url(base_url: str) -> str:
    base = str(base_url or "https://api.openai.com").strip().rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return f"{base}/models"


@router.get("/api/settings")
async def get_settings():
    """获取完整配置"""
    return config_service.get()


@router.put("/api/settings")
async def update_settings(body: dict[str, Any]):
    """更新配置"""
    result = config_service.update(body)
    if not bool((result.get("reverse_proxy") or {}).get("remember_keys")):
        from ..services.proxy_auth_service import proxy_auth_service
        proxy_auth_service.forget_plain_keys()
    return result


@router.post("/api/settings/test-proxy")
async def test_proxy(body: dict[str, Any]):
    """测试代理可用性和延迟"""
    proxy = str(body.get("proxy") or config_service.get_proxy() or "").strip()
    url = str(body.get("url") or "https://chatgpt.com/cdn-cgi/trace").strip()
    started = time.perf_counter()
    session = create_session(proxy)
    try:
        resp = session.get(url, timeout=12)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": 200 <= resp.status_code < 400,
            "status": resp.status_code,
            "latency_ms": latency_ms,
            "http_version": config_service.get_http_version(),
            "target": url,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": 0,
            "latency_ms": latency_ms,
            "http_version": config_service.get_http_version(),
            "target": url,
            "error": str(exc)[:300],
        }
    finally:
        session.close()


@router.get("/api/settings/upstream-models")
async def upstream_models(upstream_base_url: str = ""):
    """从配置的上游 OpenAI 兼容服务读取模型列表。"""
    configured = config_service.get_reverse_proxy_config()
    source = str(upstream_base_url or configured.get("upstream_base_url") or "https://api.openai.com").strip()
    proxy = config_service.get_proxy()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = request_local_retry(lambda index: requests.get(_models_url(source), timeout=20 + (10 if index else 0), proxies=proxies))
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"upstream HTTP {resp.status_code}: {resp.text[:300]}")
        payload = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    models = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                model_id = str(item.get("id") or "").strip()
                if model_id:
                    models.append(model_id)
    return {"models": sorted(set(models)), "source": _models_url(source)}
