"""代理纯净度检测 API 路由 — 流式返回"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config_service import config_service
from ..proxy_check_service import check_proxy_purity_stream

router = APIRouter()


class ProxyCheckRequest(BaseModel):
    proxy: str = ""


@router.post("/api/proxy/check-purity")
async def proxy_check_purity(body: ProxyCheckRequest):
    """流式执行代理纯净度检测，逐项返回结果"""
    proxy = (body.proxy or config_service.get_proxy() or "").strip()
    return StreamingResponse(
        check_proxy_purity_stream(proxy),
        media_type="application/x-ndjson",
    )
