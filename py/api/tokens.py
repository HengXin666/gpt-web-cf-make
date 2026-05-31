"""Token 保活 API 路由 - 刷新、续期、统计"""

from __future__ import annotations

from fastapi import APIRouter

from ..services.token_refresh_service import token_refresh_service
from .accounts import BatchIdsRequest

router = APIRouter()


@router.post("/api/tokens/refresh/{account_id}")
async def refresh_single_token(account_id: str):
    """刷新单个账号的 Token"""
    result = token_refresh_service.refresh_single(account_id)
    return result


@router.post("/api/tokens/batch-refresh")
async def batch_refresh_tokens(body: BatchIdsRequest):
    """批量刷新 Token - 支持缩减重试（仅重试失败项）"""
    result = token_refresh_service.batch_refresh(body.ids)
    return result


@router.post("/api/tokens/renew-expiring")
async def renew_expiring_tokens():
    """续期所有即将过期的 Token"""
    from ..services.config_service import config_service
    config = config_service.get_token_refresh_config()
    expiring_days = int(config.get("expiring_days") or 5)
    result = token_refresh_service.renew_expiring(expiring_days)
    return result


@router.get("/api/tokens/stats")
async def get_token_stats():
    """获取 Token 健康统计"""
    return token_refresh_service.get_token_stats()
