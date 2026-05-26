"""OpenAI 兼容反代 API 和管理接口。"""

from __future__ import annotations

import asyncio
import queue
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..account_service import account_service
from ..config_service import config_service
from ..proxy_auth_service import proxy_auth_service
from ..proxy_live_service import proxy_live_service
from ..proxy_usage_service import proxy_usage_service
from ..reverse_proxy_service import reverse_proxy_service

router = APIRouter()


class CreateProxyKeyRequest(BaseModel):
    name: str = ""


class UpdateProxyKeyRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None


def _extract_bearer(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _require_proxy_key(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    key = _extract_bearer(authorization) or str(x_api_key or "").strip()
    item = proxy_auth_service.validate(key)
    if item:
        return item
    raise HTTPException(
        status_code=401,
        detail={"error": {"message": "invalid api key", "type": "auth_error", "code": "invalid_api_key"}},
    )


@router.get("/api/proxy/status")
async def proxy_status(request: Request):
    """获取反代状态和推荐 Base URL。"""
    config = config_service.get_reverse_proxy_config()
    accounts = account_service.list_proxy_candidates()
    base_url = str(request.base_url).rstrip("/")
    return {
        "enabled": bool(config.get("enabled", True)),
        "base_url": base_url,
        "v1_base_url": f"{base_url}/v1",
        "upstream_base_url": config.get("upstream_base_url") or "https://api.openai.com",
        "strategy": config.get("strategy") or "round_robin",
        "timeout_seconds": int(config.get("timeout_seconds") or 120),
        "max_retries": int(config.get("max_retries") or 2),
        "available_accounts": len(accounts),
        "keys": len(proxy_auth_service.list_keys()),
    }


@router.get("/api/proxy/keys")
async def list_proxy_keys():
    return {"items": proxy_auth_service.list_keys()}


@router.post("/api/proxy/keys")
async def create_proxy_key(body: CreateProxyKeyRequest):
    return proxy_auth_service.create_key(body.name)


@router.patch("/api/proxy/keys/{key_id}")
async def update_proxy_key(key_id: str, body: UpdateProxyKeyRequest):
    result = proxy_auth_service.update_key(key_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="key not found")
    return result


@router.delete("/api/proxy/keys/{key_id}")
async def delete_proxy_key(key_id: str):
    return {"deleted": proxy_auth_service.delete_key(key_id)}


@router.get("/api/proxy/usage")
async def proxy_usage(limit: int = 5000):
    return proxy_usage_service.summary(limit)


@router.get("/api/proxy/usage-accounts")
async def proxy_usage_accounts(limit: int = 5000):
    return proxy_usage_service.account_summary(limit)


@router.get("/api/proxy/usage-series")
async def proxy_usage_series(minutes: int = 240, bucket_seconds: int = 60):
    return proxy_usage_service.series(minutes, bucket_seconds)


@router.get("/api/proxy/events")
async def proxy_events(request: Request):
    subscriber = proxy_live_service.subscribe()

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.to_thread(subscriber.get, True, 15)
                    yield f"data: {payload}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            proxy_live_service.unsubscribe(subscriber)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.api_route("/v1", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def openai_compatible_proxy(
    request: Request,
    path: str = "",
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    api_key = _require_proxy_key(authorization, x_api_key)
    return await reverse_proxy_service.proxy(request, path, api_key)
