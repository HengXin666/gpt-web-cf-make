"""注册机 API 路由 - 配置、启停、SSE 事件流"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..register_service import register_service

router = APIRouter()


class RegisterConfigUpdate(BaseModel):
    mail: dict[str, Any] | None = None
    proxy: str | None = None
    total: int | None = None
    threads: int | None = None
    mode: str | None = None
    target_quota: int | None = None
    target_available: int | None = None
    check_interval: int | None = None


@router.get("/api/register/config")
async def get_register_config():
    """获取注册配置"""
    return register_service.get()


@router.put("/api/register/config")
async def update_register_config(body: RegisterConfigUpdate):
    """更新注册配置"""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return register_service.update(updates)


@router.post("/api/register/start")
async def start_register():
    """启动注册任务"""
    return register_service.start()


@router.post("/api/register/stop")
async def stop_register():
    """停止注册任务"""
    return register_service.stop()


@router.post("/api/register/reset")
async def reset_register():
    """重置注册统计"""
    return register_service.reset()


@router.get("/api/register/events")
async def register_events():
    """SSE 事件流 - 实时推送注册状态（每500ms，仅在变化时推送）"""

    async def stream():
        last_payload = ""
        while True:
            payload = json.dumps(register_service.get(), ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"data: {payload}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")
