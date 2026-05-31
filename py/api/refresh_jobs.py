"""前端刷新任务 API - 创建任务并通过 SSE 输出逐账号结果。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services.refresh_job_service import refresh_job_service

router = APIRouter()


class RefreshJobRequest(BaseModel):
    action: str = "quota"
    ids: list[str]


@router.post("/api/refresh-jobs")
async def create_refresh_job(body: RefreshJobRequest):
    return refresh_job_service.create(body.action, body.ids)


@router.get("/api/refresh-jobs/{job_id}/events")
async def refresh_job_events(job_id: str):
    return StreamingResponse(
        refresh_job_service.events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
