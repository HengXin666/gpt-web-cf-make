"""导出 API 路由 - 对接 chatgpt2api 和 infinite-canvas"""

from __future__ import annotations

from fastapi import APIRouter

from ..export_service import export_to_chatgpt2api, export_to_infinite_canvas
from .accounts import BatchIdsRequest

router = APIRouter()


@router.post("/api/export/chatgpt2api")
async def export_chatgpt2api(body: BatchIdsRequest):
    """导出为 chatgpt2api 兼容格式"""
    return export_to_chatgpt2api(body.ids if body.ids else None)


@router.post("/api/export/infinite-canvas")
async def export_infinite_canvas(body: BatchIdsRequest):
    """导出为 infinite-canvas Model Channel 配置并推送"""
    return export_to_infinite_canvas(body.ids if body.ids else None)
