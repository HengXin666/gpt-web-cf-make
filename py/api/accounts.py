"""账号管理 API 路由 - 列表、统计、导入导出、批量操作"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..account_service import account_service

router = APIRouter()


class BatchIdsRequest(BaseModel):
    ids: list[str]


class ImportRequest(BaseModel):
    accounts: list[dict[str, Any]]


class UpdateAccountRequest(BaseModel):
    tags: list[str] | None = None
    notes: str | None = None
    status: str | None = None


@router.get("/api/accounts")
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    status: str = Query(""),
    search: str = Query(""),
    tags: str = Query(""),
    sort: str = Query("import_desc"),
):
    """分页查询账号列表"""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return account_service.list_accounts(page=page, page_size=page_size, status=status, search=search, tags=tag_list, sort=sort)


@router.get("/api/accounts/stats")
async def get_account_stats():
    """获取账号统计信息"""
    return account_service.get_stats()


@router.get("/api/accounts/{account_id}")
async def get_account(account_id: str):
    """获取单个账号详情"""
    account = account_service.get_account(account_id)
    if not account:
        return {"error": "account not found"}
    return account


@router.post("/api/accounts/import")
async def import_accounts(body: ImportRequest):
    """批量导入账号"""
    return account_service.import_json(body.accounts)


@router.post("/api/accounts/export")
async def export_accounts(body: BatchIdsRequest):
    """批量导出账号（空 ids 则导出全部）"""
    ids = body.ids if body.ids else None
    accounts = account_service.export_json(ids)
    return {"accounts": accounts, "count": len(accounts)}


@router.post("/api/accounts/batch-delete")
async def batch_delete(body: BatchIdsRequest):
    """批量删除账号"""
    return account_service.delete_accounts(body.ids)


@router.post("/api/accounts/batch-refresh-quota")
async def batch_refresh_quota(body: BatchIdsRequest):
    """批量刷新账号配额和状态 - 调用 OpenAI Backend API"""
    return account_service.batch_refresh_quotas(body.ids)


@router.post("/api/accounts/{account_id}/refresh-quota")
async def refresh_account_quota(account_id: str):
    """刷新单个账号配额和状态"""
    return account_service.refresh_account_quota(account_id)


@router.patch("/api/accounts/{account_id}")
async def update_account(account_id: str, body: UpdateAccountRequest):
    """更新账号信息"""
    updates = {}
    if body.tags is not None:
        updates["tags"] = body.tags
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.status is not None:
        updates["status"] = body.status
    result = account_service.update_account(account_id, updates)
    if not result:
        return {"error": "account not found"}
    return result


class ExportErrorsRequest(BaseModel):
    accounts: list[dict[str, Any]]


@router.post("/api/accounts/export-errors")
async def export_errors(body: ExportErrorsRequest):
    """将异常账号追加导出到 data/error/YY-MM-DD.json"""
    tz = timezone(timedelta(hours=8))
    date_str = datetime.now(tz).strftime("%y-%m-%d")
    error_dir = Path("data/error")
    error_dir.mkdir(parents=True, exist_ok=True)
    file_path = error_dir / f"{date_str}.json"

    # 读取已有数据
    existing: list[dict[str, Any]] = []
    if file_path.exists():
        try:
            existing = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []

    existing_ids = {a.get("id") for a in existing}
    new_accounts = [a for a in body.accounts if a.get("id") not in existing_ids]
    if not new_accounts:
        return {"file": str(file_path), "count": 0, "total": len(existing)}

    merged = existing + new_accounts
    file_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"file": str(file_path), "count": len(new_accounts), "total": len(merged)}
