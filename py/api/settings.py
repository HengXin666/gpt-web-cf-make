"""设置 API 路由 - 全局配置读写"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..config_service import config_service

router = APIRouter()


@router.get("/api/settings")
async def get_settings():
    """获取完整配置"""
    return config_service.get()


@router.put("/api/settings")
async def update_settings(body: dict[str, Any]):
    """更新配置"""
    return config_service.update(body)
