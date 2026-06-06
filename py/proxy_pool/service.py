"""代理池服务 - 节点管理、订阅同步、测试、代理解析"""

from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from pathlib import Path
from threading import RLock, Thread
from typing import Any, Generator
from urllib.parse import urlparse

from ..services.config_service import config_service, DATA_DIR
from .models import ProxyNode
from .parser import parse_subscription, proxy_node_to_url

logger = logging.getLogger(__name__)

PROXY_POOL_FILE = DATA_DIR / "proxy_pool.json"

# curl_cffi 原生支持的协议 — 可以直接用 session.proxies 测试
_NATIVE_PROTOCOLS = {"http", "https", "socks5"}

# GPT 可达性检测端点
_GPT_ENDPOINTS = [
    ("ChatGPT Web", "https://chatgpt.com/cdn-cgi/trace"),
    ("OpenAI API", "https://api.openai.com/v1/models"),
]


class ProxyPoolService:
    """代理池服务 - 线程安全"""

    def __init__(self, store_file: Path = PROXY_POOL_FILE):
        self._store_file = store_file
        self._lock = RLock()
        self._nodes: dict[str, ProxyNode] = {}
        self._subscriptions: list[dict[str, Any]] = []
        self._round_robin_index: int = 0
        self._auto_refresh_thread: Thread | None = None
        self._auto_refresh_stop = False
        self._load()
        self._start_auto_refresh()

    # ── 持久化 ──────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._store_file.exists():
                data = json.loads(self._store_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for item in data.get("nodes") or []:
                        node = ProxyNode.from_dict(item)
                        if node.id:
                            self._nodes[node.id] = node
                    subs = data.get("subscriptions") or []
                    if isinstance(subs, list):
                        self._subscriptions = [s for s in subs if isinstance(s, dict)]
        except Exception:
            pass

    def _save(self) -> None:
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "subscriptions": self._subscriptions,
        }
        self._store_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # ── 自动刷新 ────────────────────────────────────────────────

    def _start_auto_refresh(self) -> None:
        pool_cfg = config_service.get_proxy_pool_config()
        if not pool_cfg.get("auto_refresh_enabled"):
            return
        if self._auto_refresh_thread and self._auto_refresh_thread.is_alive():
            return
        self._auto_refresh_stop = False
        self._auto_refresh_thread = Thread(target=self._auto_refresh_loop, daemon=True, name="proxy-pool-auto-refresh")
        self._auto_refresh_thread.start()

    def _auto_refresh_loop(self) -> None:
        while not self._auto_refresh_stop:
            pool_cfg = config_service.get_proxy_pool_config()
            interval = max(5, int(pool_cfg.get("auto_refresh_interval_minutes") or 60))
            for _ in range(interval * 60):
                if self._auto_refresh_stop:
                    return
                time.sleep(1)
            try:
                result = self.sync_all_subscriptions()
                logger.info(f"[proxy-pool] 自动刷新完成: {result}")
            except Exception as e:
                logger.warning(f"[proxy-pool] 自动刷新失败: {e}")

    def restart_auto_refresh(self) -> None:
        self.stop_auto_refresh()
        time.sleep(0.5)
        self._start_auto_refresh()

    def stop_auto_refresh(self) -> None:
        self._auto_refresh_stop = True
        if self._auto_refresh_thread and self._auto_refresh_thread.is_alive():
            self._auto_refresh_thread.join(timeout=3)
            self._auto_refresh_thread = None

    def get_auto_refresh_status(self) -> dict[str, Any]:
        pool_cfg = config_service.get_proxy_pool_config()
        return {
            "enabled": bool(pool_cfg.get("auto_refresh_enabled")),
            "interval_minutes": int(pool_cfg.get("auto_refresh_interval_minutes") or 60),
            "running": self._auto_refresh_thread is not None and self._auto_refresh_thread.is_alive(),
        }

    # ── 节点 CRUD ───────────────────────────────────────────────

    def list_nodes(
        self,
        enabled: bool | None = None,
        search: str = "",
        protocol: str = "",
        pool: str = "",
        sort: str = "name_asc",
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        with self._lock:
            items = [deepcopy(n.to_dict()) for n in self._nodes.values()]

        if enabled is not None:
            items = [n for n in items if n.get("enabled") == enabled]
        if protocol:
            items = [n for n in items if n.get("protocol") == protocol]
        if pool:
            items = [n for n in items if n.get("pool") == pool]
        if search:
            s = search.lower()
            items = [
                n for n in items
                if s in n.get("name", "").lower()
                or s in n.get("server", "").lower()
                or s in n.get("country", "").lower()
                or s in n.get("isp", "").lower()
            ]

        sort_map = {
            "name_asc": ("name", False),
            "name_desc": ("name", True),
            "latency_asc": ("latency_ms", False),
            "latency_desc": ("latency_ms", True),
            "score_asc": ("score", False),
            "score_desc": ("score", True),
            "created_asc": ("created_at", False),
            "created_desc": ("created_at", True),
        }
        key, reverse = sort_map.get(sort, sort_map["name_asc"])
        items.sort(key=lambda n: n.get(key, "") if n.get(key) is not None else "", reverse=reverse)

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "items": items[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        with self._lock:
            node = self._nodes.get(node_id)
            return deepcopy(node.to_dict()) if node else None

    def add_nodes(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"added": 0, "skipped": 0}

        with self._lock:
            existing_keys = {(n.server, n.port, n.protocol) for n in self._nodes.values()}
            added = 0
            skipped = 0

            for item in items:
                server = str(item.get("server") or "").strip()
                port = int(item.get("port") or 0)
                protocol = str(item.get("protocol") or "").strip().lower()
                if not server or not port:
                    skipped += 1
                    continue

                dedup_key = (server, port, protocol)
                if dedup_key in existing_keys:
                    skipped += 1
                    continue

                proxy_url = str(item.get("proxy_url") or "").strip()
                if not proxy_url and protocol in _NATIVE_PROTOCOLS:
                    from .parser import _build_url
                    proxy_url = _build_url(
                        protocol, server, port,
                        str(item.get("username") or ""),
                        str(item.get("password") or ""),
                    )

                node = ProxyNode.from_dict({
                    **item,
                    "id": _new_id(), "server": server, "port": port,
                    "protocol": protocol, "proxy_url": proxy_url,
                    "pool": str(item.get("pool") or "api"),
                    "created_at": _now(), "updated_at": _now(),
                })
                self._nodes[node.id] = node
                existing_keys.add(dedup_key)
                added += 1

            if added:
                self._save()
        return {"added": added, "skipped": skipped}

    def update_node(self, node_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return None
            current = node.to_dict()
            current.update({k: v for k, v in updates.items() if k != "id"})
            current["updated_at"] = _now()
            updated = ProxyNode.from_dict(current)
            updated.id = node_id
            self._nodes[node_id] = updated
            self._save()
            return deepcopy(updated.to_dict())

    def batch_set_pool(self, ids: list[str], pool: str) -> dict[str, Any]:
        """批量设置节点池分类。"""
        if pool not in ("api", "register"):
            return {"ok": False, "error": "池类型必须为 api 或 register"}
        with self._lock:
            changed = 0
            for nid in ids:
                node = self._nodes.get(nid)
                if node:
                    node.pool = pool
                    node.updated_at = _now()
                    changed += 1
            if changed:
                self._save()
        return {"ok": True, "changed": changed}

    def delete_nodes(self, ids: list[str]) -> dict[str, Any]:
        with self._lock:
            removed = sum(1 for nid in ids if nid in self._nodes and not self._nodes.pop(nid))
            if removed:
                self._save()
        return {"removed": removed}

    # ── 订阅管理 ────────────────────────────────────────────────

    def list_subscriptions(self) -> list[dict[str, Any]]:
        with self._lock:
            result = []
            for sub in self._subscriptions:
                item = deepcopy(sub)
                sub_id = sub.get("id", "")
                item["node_count"] = sum(1 for n in self._nodes.values() if n.subscription_id == sub_id)
                result.append(item)
            return result

    def import_subscription(self, url: str, name: str = "", sub_type: str = "auto",
                             pool: str = "api") -> dict[str, Any]:
        """拉取订阅 URL，解析节点，合并到池中。"""
        url = (url or "").strip()
        if not url:
            return {"ok": False, "error": "URL 为空"}

        try:
            from ..shared.http_client import create_session
            proxy = config_service.get_proxy()
            session = create_session(proxy)
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            raw = resp.text
        except Exception as e:
            return {"ok": False, "error": f"拉取订阅失败: {e}"}

        nodes = parse_subscription(raw, sub_type)
        if not nodes:
            return {"ok": False, "error": "未解析到任何节点"}

        sub_id = _new_id()
        sub_name = name or self._guess_sub_name(url, nodes)
        sub_record: dict[str, Any] = {
            "id": sub_id, "url": url, "name": sub_name,
            "type": sub_type, "pool": pool, "last_synced_at": _now(),
        }

        with self._lock:
            self._subscriptions.append(sub_record)
            for node in nodes:
                node.subscription_id = sub_id
                node.pool = pool
                if not node.name:
                    node.name = f"{node.server}:{node.port}"

            existing_keys = {(n.server, n.port, n.protocol) for n in self._nodes.values()}
            added = 0
            updated_count = 0
            for node in nodes:
                dedup_key = (node.server, node.port, node.protocol)
                if dedup_key in existing_keys:
                    for existing in self._nodes.values():
                        if (existing.server, existing.port, existing.protocol) == dedup_key:
                            # 只更新订阅相关，保留用户自定义字段
                            existing.name = node.name or existing.name
                            existing.extra = node.extra or existing.extra
                            existing.proxy_url = node.proxy_url or existing.proxy_url
                            existing.subscription_id = sub_id
                            # existing.pool 不变 (用户可能已手动改)
                            # existing.enabled 不变
                            # existing.score, grade, latency_ms 不变 (旧测试结果保留)
                            existing.updated_at = _now()
                            updated_count += 1
                            break
                else:
                    self._nodes[node.id] = node
                    existing_keys.add(dedup_key)
                    added += 1
            self._save()

        return {
            "ok": True, "subscription_id": sub_id, "name": sub_name,
            "total_parsed": len(nodes), "added": added, "updated": updated_count,
        }

    def sync_subscription(self, sub_id: str) -> dict[str, Any]:
        with self._lock:
            sub = next((s for s in self._subscriptions if s.get("id") == sub_id), None)
        if not sub:
            return {"ok": False, "error": "订阅不存在"}

        url = str(sub.get("url") or "")
        name = str(sub.get("name") or "")
        sub_type = str(sub.get("type") or "auto")

        # 拉取新数据
        from ..shared.http_client import create_session
        try:
            proxy = config_service.get_proxy()
            session = create_session(proxy)
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            raw = resp.text
        except Exception as e:
            return {"ok": False, "error": f"拉取订阅失败: {e}"}

        nodes = parse_subscription(raw, sub_type)
        if not nodes:
            return {"ok": False, "error": "未解析到任何节点"}

        with self._lock:
            new_keys: set[tuple] = set()
            for nd in nodes:
                if not nd.server or not nd.port:
                    continue
                key = (nd.server, nd.port, nd.protocol)
                new_keys.add(key)
                existing = next((n for n in self._nodes.values() if (n.server, n.port, n.protocol) == key), None)
                if existing:
                    existing.name = nd.name or existing.name
                    existing.extra = nd.extra or existing.extra
                    existing.proxy_url = nd.proxy_url or existing.proxy_url
                    existing.subscription_id = sub_id
                    existing.updated_at = _now()
                else:
                    nd.subscription_id = sub_id
                    nd.updated_at = _now()
                    self._nodes[nd.id] = nd

            # 删除不再存在的节点
            from ..services.account_service import account_service
            accounts = account_service.list_accounts(page=1, page_size=99999)["items"]
            assigned_ids = {a.get("proxy_node_id") for a in accounts}
            for nid, n in list(self._nodes.items()):
                if n.subscription_id != sub_id:
                    continue
                key = (n.server, n.port, n.protocol)
                if key not in new_keys:
                    if nid in assigned_ids or n.last_tested_at or n.score >= 0:
                        n.enabled = False
                        n.last_error = "订阅中已移除"
                    else:
                        del self._nodes[nid]

            self._save()

        return {"ok": True, "subscription_id": sub_id, "total_parsed": len(nodes)}

    def sync_all_subscriptions(self) -> dict[str, Any]:
        with self._lock:
            sub_ids = [s.get("id", "") for s in self._subscriptions]
        results = [self.sync_subscription(sid) for sid in sub_ids if sid]
        synced = sum(1 for r in results if r.get("ok"))
        return {"synced": synced, "total": len(sub_ids), "results": results}

    def remove_subscription(self, sub_id: str) -> dict[str, Any]:
        with self._lock:
            before = len(self._subscriptions)
            self._subscriptions = [s for s in self._subscriptions if s.get("id") != sub_id]
            removed_nodes = 0
            for nid, n in list(self._nodes.items()):
                if n.subscription_id == sub_id:
                    del self._nodes[nid]
                    removed_nodes += 1
            if len(self._subscriptions) < before:
                self._save()
                return {"ok": True, "removed_nodes": removed_nodes}
        return {"ok": False, "error": "订阅不存在"}

    # ── 测试 ────────────────────────────────────────────────────

    def _resolve_test_proxy(self, node: ProxyNode) -> str:
        """解析测试用的代理地址。

        原生协议 (http/https/socks5) → 直接测试节点本身
        非原生协议 (vless/trojan/ss/hysteria2...) → 走全局代理（Clash/mihomo 中转）
        """
        direct = proxy_node_to_url(node)
        if direct:
            return direct
        # 非原生协议，走全局代理
        return config_service.get_proxy()

    def test_node(self, node_id: str) -> dict[str, Any]:
        """快速延迟测试 — 自动适配协议类型。"""
        with self._lock:
            node = self._nodes.get(node_id)
        if not node:
            return {"ok": False, "error": "节点不存在"}

        proxy_url = self._resolve_test_proxy(node)
        if not proxy_url:
            return {"ok": False, "error": f"协议 {node.protocol} 需要配置全局代理（Clash/mihomo）才能测试"}

        try:
            from ..shared.http_client import create_session
            session = create_session(proxy_url)
            t0 = time.perf_counter()
            resp = session.get("https://chatgpt.com/cdn-cgi/trace", timeout=10)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            ok = resp.status_code == 200

            self.update_node(node_id, {
                "latency_ms": latency_ms,
                "last_tested_at": _now(),
                "last_error": "" if ok else f"HTTP {resp.status_code}",
            })
            return {"ok": ok, "latency_ms": latency_ms, "status": resp.status_code}
        except Exception as e:
            error_msg = str(e)[:200]
            self.update_node(node_id, {"last_error": error_msg, "last_tested_at": _now()})
            return {"ok": False, "error": error_msg}

    def test_node_purity(self, node_id: str) -> Generator[str, None, None]:
        """完整纯净度检测 + GPT 可达性验证，流式 NDJSON。"""
        with self._lock:
            node = self._nodes.get(node_id)
        if not node:
            yield json.dumps({"step": "error", "error": "节点不存在"}, ensure_ascii=False) + "\n"
            return

        proxy_url = self._resolve_test_proxy(node)
        if not proxy_url:
            yield json.dumps({"step": "error", "error": f"协议 {node.protocol} 需要配置全局代理"}, ensure_ascii=False) + "\n"
            return

        from ..services.proxy_check_service import check_proxy_purity_stream
        final_result: dict[str, Any] = {}

        for event_str in check_proxy_purity_stream(proxy_url):
            yield event_str
            try:
                event = json.loads(event_str.strip())
                if event.get("step") == "done":
                    final_result = event
            except Exception:
                pass

        if final_result:
            # 检查 AI 服务可达性
            ai_services = final_result.get("ai_services", [])
            gpt_reachable = any(
                s.get("reachable") and s.get("name") == "ChatGPT Web"
                for s in ai_services
            )

            updates: dict[str, Any] = {
                "score": final_result.get("score", -1),
                "grade": final_result.get("grade", ""),
                "country": final_result.get("country", ""),
                "city": final_result.get("city", ""),
                "isp": final_result.get("isp", ""),
                "ip_type": final_result.get("ip_type", ""),
                "latency_ms": next(
                    (s.get("latency_ms", -1) for s in ai_services if s.get("name") == "ChatGPT Web"),
                    node.latency_ms,
                ),
                "last_tested_at": _now(),
                "last_error": "",
            }

            # GPT 不可达 → 自动禁用
            if not gpt_reachable:
                updates["enabled"] = False
                updates["last_error"] = "GPT 不可达，已自动禁用"

            self.update_node(node_id, updates)

            # 额外发送池级别完成事件
            yield json.dumps({
                "step": "pool_done",
                "ai_reachable": gpt_reachable,
                "auto_disabled": not gpt_reachable,
                "score": updates.get("score", -1),
                "grade": updates.get("grade", ""),
            }, ensure_ascii=False) + "\n"

    def test_nodes_batch(self, ids: list[str], max_workers: int = 5,
                          auto_disable: bool = True) -> dict[str, Any]:
        """批量测试 — 支持自动禁用不可达节点。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not ids:
            return {"tested": 0, "failed": 0, "disabled": 0, "results": []}

        max_workers = min(max_workers, len(ids), 10)
        results: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.test_node, nid): nid for nid in ids}
            for future in as_completed(futures):
                node_id = futures[future]
                try:
                    result = future.result()
                    results.append({"node_id": node_id, **result})
                except Exception as e:
                    results.append({"node_id": node_id, "ok": False, "error": str(e)})

        tested = sum(1 for r in results if r.get("ok"))
        failed_ids = [r["node_id"] for r in results if not r.get("ok")]
        disabled = 0

        # 自动禁用测试失败的节点
        if auto_disable and failed_ids:
            with self._lock:
                for nid in failed_ids:
                    node = self._nodes.get(nid)
                    if node and node.enabled:
                        node.enabled = False
                        node.last_error = "批量测试不可达，已自动禁用"
                        node.updated_at = _now()
                        disabled += 1
                if disabled:
                    self._save()

        return {"tested": tested, "failed": len(failed_ids), "disabled": disabled, "results": results}

    def test_gpt_reachability(self, node_id: str) -> dict[str, Any]:
        """快速检测 GPT 可达性（仅测 ChatGPT Web + OpenAI API）。"""
        with self._lock:
            node = self._nodes.get(node_id)
        if not node:
            return {"ok": False, "error": "节点不存在"}

        proxy_url = self._resolve_test_proxy(node)
        if not proxy_url:
            return {"ok": False, "error": f"协议 {node.protocol} 需要配置全局代理"}

        try:
            from ..shared.http_client import create_session
            session = create_session(proxy_url)
            results = {}
            all_ok = True

            for name, url in _GPT_ENDPOINTS:
                try:
                    t0 = time.perf_counter()
                    resp = session.get(url, timeout=8)
                    ms = int((time.perf_counter() - t0) * 1000)
                    ok = resp.status_code < 500
                    results[name] = {"ok": ok, "latency_ms": ms, "status": resp.status_code}
                    if not ok:
                        all_ok = False
                except Exception as e:
                    results[name] = {"ok": False, "error": str(e)[:100]}
                    all_ok = False

            # 不可达 → 禁用
            if not all_ok:
                self.update_node(node_id, {
                    "enabled": False,
                    "last_error": "GPT 不可达，已自动禁用",
                    "last_tested_at": _now(),
                })
            else:
                chatgpt = results.get("ChatGPT Web", {})
                self.update_node(node_id, {
                    "latency_ms": chatgpt.get("latency_ms", -1),
                    "last_tested_at": _now(),
                    "last_error": "",
                })

            return {"ok": all_ok, "gpt_results": results, "auto_disabled": not all_ok}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── 代理解析 ────────────────────────────────────────────────

    def resolve_proxy(self, proxy_node_id: str = "", pool: str = "") -> str:
        """中央代理解析。

        优先级:
        1. 指定 node_id → 返回该节点的代理 URL
        2. 指定 pool → 从该池中轮询可用节点
        3. pool 模式 → 轮询返回可用节点
        4. 否则 → 回退全局代理
        """
        # 1. 指定节点
        if proxy_node_id:
            with self._lock:
                node = self._nodes.get(proxy_node_id)
            if node and node.enabled:
                return self._resolve_test_proxy(node)

        # 2. 指定池
        if pool:
            url = self._pick_available_node(pool=pool)
            if url:
                return url

        # 3. pool 模式
        if config_service.get_proxy_mode() == "pool":
            url = self._pick_available_node()
            if url:
                return url

        # 4. 回退全局代理
        return config_service.get_proxy()

    def resolve_proxy_with_info(self, proxy_node_id: str = "", pool: str = "") -> tuple[str, str]:
        """代理解析并返回 (proxy_url, node_display_name)，用于日志。"""
        # 1. 指定节点
        if proxy_node_id:
            with self._lock:
                node = self._nodes.get(proxy_node_id)
            if node and node.enabled:
                return self._resolve_test_proxy(node), f"{node.name} ({node.protocol}://{node.server}:{node.port})"

        # 2. 指定池
        if pool:
            with self._lock:
                candidates = [n for n in self._nodes.values() if n.enabled and n.pool == pool]
            if candidates:
                good = sorted(candidates, key=lambda n: n.latency_ms if n.latency_ms >= 0 else 99999)
                node = good[0]
                return self._resolve_test_proxy(node), f"{node.name} ({node.protocol}://{node.server}:{node.port})"

        # 3. pool 模式
        if config_service.get_proxy_mode() == "pool":
            url = self._pick_available_node()
            if url:
                with self._lock:
                    for n in self._nodes.values():
                        if n.enabled and self._resolve_test_proxy(n) == url:
                            return url, f"{n.name} ({n.protocol}://{n.server}:{n.port})"
                return url, "pool-node"

        # 4. 回退全局代理
        return config_service.get_proxy(), ""

    def _pick_available_node(self, pool: str = "") -> str:
        """轮询选择一个可用节点的代理 URL。"""
        with self._lock:
            candidates = [
                n for n in self._nodes.values()
                if n.enabled
                and (not pool or n.pool == pool)
            ]
            if not candidates:
                return ""
            good = sorted(candidates, key=lambda n: n.latency_ms if n.latency_ms >= 0 else 99999)
            pick = good[:max(1, len(good) // 2 + 1)] if len(good) > 3 else good
            self._round_robin_index = (self._round_robin_index + 1) % len(pick)
            node = pick[self._round_robin_index]
            return self._resolve_test_proxy(node)

    def get_proxy_url(self, node_id: str) -> str:
        with self._lock:
            node = self._nodes.get(node_id)
            return self._resolve_test_proxy(node) if node else ""

    def pick_random_node(self, pool: str = "") -> tuple[str, str]:
        """随机选择一个可用节点，返回 (proxy_url, display_name)。用于注册机等需要 IP 分散的场景。"""
        import random
        with self._lock:
            candidates = [
                n for n in self._nodes.values()
                if n.enabled and (not pool or n.pool == pool)
            ]
        if not candidates:
            return config_service.get_proxy(), ""
        node = random.choice(candidates)
        return self._resolve_test_proxy(node), f"{node.name} ({node.protocol}://{node.server}:{node.port})"

    # ── 注册流水线节点追踪 ──────────────────────────────────────

    def record_register_result(self, node_name: str, success: bool, error: str = "") -> None:
        """记录注册结果到对应节点。node_name 格式如 'HK-01 (http://x.x.x.x:8080)'"""
        if not node_name:
            return
        with self._lock:
            # 从 display_name 中匹配节点
            for node in self._nodes.values():
                if node_name.startswith(node.name):
                    node.register_total = (node.register_total or 0) + 1
                    node.register_last_used_at = _now()
                    if success:
                        node.register_success = (node.register_success or 0) + 1
                        # 成功后重置失败计数（说明节点恢复了）
                        node.register_otp_timeouts = 0
                        node.register_token_failures = 0
                        node.register_last_error = ""
                    else:
                        node.register_last_error = error[:500]
                        if "OTP" in error.upper() or "验证码" in error or "timeout" in error.lower():
                            node.register_otp_timeouts = (node.register_otp_timeouts or 0) + 1
                        else:
                            node.register_token_failures = (node.register_token_failures or 0) + 1
                    node.updated_at = _now()
                    self._save()
                    return

    def check_and_disable_failed_nodes(
        self, max_otp_timeouts: int = 3, max_token_failures: int = 3
    ) -> list[dict[str, Any]]:
        """检查注册池节点，超过阈值的自动禁用。返回被禁用的节点列表。"""
        disabled: list[dict[str, Any]] = []
        with self._lock:
            for node in self._nodes.values():
                if node.pool != "register" or not node.enabled:
                    continue
                otp = node.register_otp_timeouts or 0
                token = node.register_token_failures or 0
                if (max_otp_timeouts > 0 and otp >= max_otp_timeouts) or \
                   (max_token_failures > 0 and token >= max_token_failures):
                    node.enabled = False
                    node.updated_at = _now()
                    disabled.append({
                        "id": node.id,
                        "name": node.name,
                        "otp_timeouts": otp,
                        "token_failures": token,
                        "last_error": node.register_last_error,
                    })
            if disabled:
                self._save()
        return disabled

    def get_register_node_stats(self) -> list[dict[str, Any]]:
        """获取注册池所有节点的失败统计"""
        with self._lock:
            return [
                {
                    "id": n.id,
                    "name": n.name,
                    "server": n.server,
                    "port": n.port,
                    "protocol": n.protocol,
                    "enabled": n.enabled,
                    "otp_timeouts": n.register_otp_timeouts or 0,
                    "token_failures": n.register_token_failures or 0,
                    "success": n.register_success or 0,
                    "total": n.register_total or 0,
                    "last_error": n.register_last_error or "",
                    "last_used_at": n.register_last_used_at or "",
                }
                for n in self._nodes.values()
                if n.pool == "register"
            ]

    def reset_register_node_stats(self, node_id: str = "") -> dict[str, Any]:
        """重置指定节点或全部注册池节点的统计"""
        with self._lock:
            targets = (
                [self._nodes[node_id]] if node_id and node_id in self._nodes
                else [n for n in self._nodes.values() if n.pool == "register"]
            )
            for node in targets:
                node.register_otp_timeouts = 0
                node.register_token_failures = 0
                node.register_success = 0
                node.register_total = 0
                node.register_last_error = ""
                node.register_last_used_at = ""
                node.updated_at = _now()
            if targets:
                self._save()
            return {"reset": len(targets)}

    # ── 分配管理 ────────────────────────────────────────────────

    def assign_to_account(self, account_id: str, node_id: str) -> dict[str, Any]:
        from ..services.account_service import account_service
        if node_id:
            with self._lock:
                if node_id not in self._nodes:
                    return {"ok": False, "error": "节点不存在"}
        result = account_service.update_account(account_id, {"proxy_node_id": node_id})
        if result is None:
            return {"ok": False, "error": "账号不存在"}
        return {"ok": True, "account_id": account_id, "proxy_node_id": node_id}

    def assign_best_node(self, account_id: str, pool: str = "api") -> dict[str, Any]:
        """为新账号分配最优节点（按延迟+评分排序）"""
        import random
        from ..services.account_service import account_service
        with self._lock:
            candidates = [
                n for n in self._nodes.values()
                if n.enabled and n.pool == pool
            ]
        if not candidates:
            return {"ok": False, "error": f"池 {pool} 中没有可用节点"}
        # 按评分降序、延迟升序排序，取最优
        candidates.sort(key=lambda n: (
            -(n.score if n.score >= 0 else -1),
            n.latency_ms if n.latency_ms >= 0 else 99999,
        ))
        # 从 top 3 中随机选一个，避免所有新账号挤到同一个节点
        top = candidates[:min(3, len(candidates))]
        best = random.choice(top)
        result = account_service.update_account(account_id, {"proxy_node_id": best.id})
        if result is None:
            return {"ok": False, "error": "账号不存在"}
        return {
            "ok": True,
            "account_id": account_id,
            "proxy_node_id": best.id,
            "node": {
                "name": best.name or best.server,
                "server": best.server,
                "port": best.port,
                "latency_ms": best.latency_ms,
                "score": best.score,
            },
        }

    def unassign_from_account(self, account_id: str) -> dict[str, Any]:
        from ..services.account_service import account_service
        result = account_service.update_account(account_id, {"proxy_node_id": ""})
        if result is None:
            return {"ok": False, "error": "账号不存在"}
        return {"ok": True}

    def balance_assign(self, pool: str = "api", max_latency_ms: int = 1500, min_score: int = 0) -> dict[str, Any]:
        """一键平衡分配：为未分配账号自动分配节点（不修改已分配的）。
        按质量+延迟筛选，尽可能均匀分配。
        """
        import random
        from ..services.account_service import account_service

        # 取所有账号
        accounts = account_service.list_accounts(page=1, page_size=99999)["items"]

        # 未分配的账号
        unassigned = [a for a in accounts if not a.get("proxy_node_id")]
        if not unassigned:
            return {"ok": True, "assigned": 0, "message": "所有账号已分配"}

        # 符合条件的节点
        with self._lock:
            candidates = [
                n for n in self._nodes.values()
                if n.enabled and n.pool == pool
                and (max_latency_ms <= 0 or n.latency_ms < 0 or n.latency_ms <= max_latency_ms)
                and (min_score <= 0 or n.score < 0 or n.score >= min_score)
            ]

        if not candidates:
            return {"ok": False, "error": f"池 {pool} 中没有符合条件的节点（延迟<{max_latency_ms}ms，评分>{min_score}）"}

        # 打乱节点列表，尽可能均匀分配
        random.shuffle(candidates)
        assigned = 0
        for acc in unassigned:
            node = candidates[assigned % len(candidates)]
            account_service.update_account(acc["id"], {"proxy_node_id": node.id})
            assigned += 1

        return {
            "ok": True,
            "assigned": assigned,
            "total_unassigned": len(unassigned),
            "nodes_available": len(candidates),
            "pool": pool,
        }

    def get_assignments(self) -> list[dict[str, Any]]:
        from ..services.account_service import account_service
        accounts = account_service.list_accounts(page=1, page_size=99999)["items"]

        # 加载用量数据
        try:
            from ..services.proxy_usage_service import proxy_usage_service
            usage_index = proxy_usage_service.account_usage_index()
        except Exception:
            usage_index = {}

        with self._lock:
            nodes = self._nodes

        result = []
        for acc in accounts:
            node_id = str(acc.get("proxy_node_id") or "")
            node_name = ""
            node_latency = -1
            if node_id and node_id in nodes:
                n = nodes[node_id]
                node_name = f"{n.name} ({n.pool})"
                node_latency = n.latency_ms

            usage = usage_index.get(str(acc.get("id") or "")) or usage_index.get(str(acc.get("email") or "").lower()) or {}

            result.append({
                "account_id": acc.get("id", ""),
                "email": acc.get("email", ""),
                "proxy_node_id": node_id,
                "node_name": node_name,
                "node_latency_ms": node_latency,
                "total_tokens": usage.get("usage_total_tokens", 0),
                "requests": usage.get("requests", 0),
                "failed": usage.get("failed", 0),
            })
        return result

    # ── 统计 ────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            nodes = list(self._nodes.values())

        total = len(nodes)
        enabled = sum(1 for n in nodes if n.enabled)
        tested = sum(1 for n in nodes if n.last_tested_at)
        scores = [n.score for n in nodes if n.score >= 0]
        avg_score = int(sum(scores) / len(scores)) if scores else 0

        by_protocol: dict[str, int] = {}
        by_country: dict[str, int] = {}
        by_pool: dict[str, int] = {}
        for n in nodes:
            by_protocol[n.protocol] = by_protocol.get(n.protocol, 0) + 1
            by_pool[n.pool] = by_pool.get(n.pool, 0) + 1
            if n.country:
                by_country[n.country] = by_country.get(n.country, 0) + 1

        from ..services.account_service import account_service
        accounts = account_service.list_accounts(page=1, page_size=99999)["items"]
        assigned = sum(1 for a in accounts if a.get("proxy_node_id"))

        return {
            "total_nodes": total,
            "enabled_nodes": enabled,
            "tested_nodes": tested,
            "avg_score": avg_score,
            "by_protocol": by_protocol,
            "by_country": by_country,
            "by_pool": by_pool,
            "assigned_accounts": assigned,
        }

    # ── 工具 ────────────────────────────────────────────────────

    @staticmethod
    def _guess_sub_name(url: str, nodes: list[ProxyNode]) -> str:
        try:
            parsed = urlparse(url)
            host = parsed.hostname or "订阅"
            countries = {n.country for n in nodes[:5] if n.country}
            if len(countries) == 1:
                return f"{countries.pop()} - {host}"
            return host
        except Exception:
            return "订阅"


# 需要延迟导入避免循环
from ..shared.models import _now, _new_id

# 全局单例
proxy_pool_service = ProxyPoolService()
