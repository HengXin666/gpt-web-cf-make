"""代理池 API 路由 — 节点管理、订阅、测试、分配、池分类"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..proxy_pool import proxy_pool_service

router = APIRouter(prefix="/api/proxy-pool", tags=["proxy-pool"])


# ── 请求模型 ─────────────────────────────────────────────────────

class AddNodesRequest(BaseModel):
    items: list[dict] = []


class DeleteNodesRequest(BaseModel):
    ids: list[str] = []


class ImportSubscriptionRequest(BaseModel):
    url: str = ""
    name: str = ""
    type: str = "auto"
    pool: str = "api"


class BatchTestRequest(BaseModel):
    ids: list[str] = []
    max_workers: int = 5
    auto_disable: bool = True


class BatchSetPoolRequest(BaseModel):
    ids: list[str] = []
    pool: str = "api"


class AssignRequest(BaseModel):
    account_id: str = ""
    node_id: str = ""


class AutoRefreshRequest(BaseModel):
    enabled: bool = False
    interval_minutes: int = 60
    auto_assign_new_accounts: bool | None = None


# ── 节点 CRUD ────────────────────────────────────────────────────

@router.get("/nodes")
async def list_nodes(
    enabled: bool | None = None,
    search: str = "",
    protocol: str = "",
    pool: str = "",
    sort: str = "name_asc",
    page: int = 1,
    page_size: int = 50,
):
    return proxy_pool_service.list_nodes(enabled=enabled, search=search, protocol=protocol, pool=pool, sort=sort, page=page, page_size=page_size)


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    node = proxy_pool_service.get_node(node_id)
    if not node:
        return {"error": "节点不存在"}
    return node


@router.post("/nodes")
async def add_nodes(body: AddNodesRequest):
    return proxy_pool_service.add_nodes(body.items)


@router.patch("/nodes/{node_id}")
async def update_node(node_id: str, body: dict):
    result = proxy_pool_service.update_node(node_id, body)
    if not result:
        return {"error": "节点不存在"}
    return result


@router.delete("/nodes")
async def delete_nodes(body: DeleteNodesRequest):
    return proxy_pool_service.delete_nodes(body.ids)


# ── 池分类 ──────────────────────────────────────────────────────

@router.post("/nodes/batch-set-pool")
async def batch_set_pool(body: BatchSetPoolRequest):
    return proxy_pool_service.batch_set_pool(body.ids, body.pool)


# ── 订阅管理 ─────────────────────────────────────────────────────

@router.get("/subscriptions")
async def list_subscriptions():
    return proxy_pool_service.list_subscriptions()


@router.post("/subscriptions")
async def import_subscription(body: ImportSubscriptionRequest):
    return proxy_pool_service.import_subscription(body.url, body.name, body.type, body.pool)


@router.post("/subscriptions/{sub_id}/sync")
async def sync_subscription(sub_id: str):
    return proxy_pool_service.sync_subscription(sub_id)


@router.post("/subscriptions/sync-all")
async def sync_all_subscriptions():
    return proxy_pool_service.sync_all_subscriptions()


@router.delete("/subscriptions/{sub_id}")
async def remove_subscription(sub_id: str):
    return proxy_pool_service.remove_subscription(sub_id)


# ── 测试 ─────────────────────────────────────────────────────────

@router.post("/nodes/{node_id}/test")
async def test_node(node_id: str):
    return proxy_pool_service.test_node(node_id)


@router.post("/nodes/{node_id}/test-purity")
async def test_node_purity(node_id: str):
    return StreamingResponse(
        proxy_pool_service.test_node_purity(node_id),
        media_type="application/x-ndjson",
    )


@router.post("/nodes/{node_id}/test-gpt")
async def test_gpt_reachability(node_id: str):
    return proxy_pool_service.test_gpt_reachability(node_id)


@router.post("/nodes/batch-test")
async def batch_test_nodes(body: BatchTestRequest):
    return proxy_pool_service.test_nodes_batch(body.ids, body.max_workers, body.auto_disable)


# ── 分配管理 ─────────────────────────────────────────────────────

@router.get("/assignments")
async def get_assignments():
    return proxy_pool_service.get_assignments()


class BalanceAssignRequest(BaseModel):
    pool: str = "api"
    max_latency_ms: int = 1500
    min_score: int = 0


@router.post("/balance-assign")
async def balance_assign(body: BalanceAssignRequest):
    return proxy_pool_service.balance_assign(body.pool, body.max_latency_ms, body.min_score)


@router.post("/assign")
async def assign_node(body: AssignRequest):
    return proxy_pool_service.assign_to_account(body.account_id, body.node_id)


@router.delete("/assign/{account_id}")
async def unassign_node(account_id: str):
    return proxy_pool_service.unassign_from_account(account_id)


# ── 统计 ─────────────────────────────────────────────────────────

@router.get("/stats")
async def get_pool_stats():
    return proxy_pool_service.get_stats()


# ── 自动刷新 ─────────────────────────────────────────────────────

@router.get("/auto-refresh")
async def get_auto_refresh():
    from ..services.config_service import config_service
    result = proxy_pool_service.get_auto_refresh_status()
    pool_cfg = config_service.get_proxy_pool_config()
    result["auto_assign_new_accounts"] = bool(pool_cfg.get("auto_assign_new_accounts"))
    return result


@router.post("/auto-refresh")
async def update_auto_refresh(body: AutoRefreshRequest):
    from ..services.config_service import config_service
    updates = {
        "auto_refresh_enabled": body.enabled,
        "auto_refresh_interval_minutes": max(5, body.interval_minutes),
    }
    if body.auto_assign_new_accounts is not None:
        updates["auto_assign_new_accounts"] = body.auto_assign_new_accounts
    config_service.update({"proxy_pool": updates})
    proxy_pool_service.restart_auto_refresh()
    result = proxy_pool_service.get_auto_refresh_status()
    pool_cfg = config_service.get_proxy_pool_config()
    result["auto_assign_new_accounts"] = bool(pool_cfg.get("auto_assign_new_accounts"))
    return result


# ── 节点用量统计 ────────────────────────────────────────────────

@router.get("/node-usage")
async def get_node_usage_stats():
    from ..services.proxy_usage_service import proxy_usage_service
    return proxy_usage_service.node_usage_stats()
