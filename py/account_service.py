"""账号服务 - 管理 accounts.json，提供 CRUD、批量操作、分页、去重"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from .config_service import DATA_DIR
from .shared.models import Account, _now, _new_id

ACCOUNTS_FILE = DATA_DIR / "accounts.json"


class AccountService:
    """账号池服务 - 使用 id -> Account 字典存储，线程安全"""

    def __init__(self, store_file: Path = ACCOUNTS_FILE):
        self._store_file = store_file
        self._lock = RLock()
        self._accounts: dict[str, Account] = {}
        self._load()

    def _load(self) -> None:
        """从 JSON 文件加载账号"""
        try:
            if self._store_file.exists():
                data = json.loads(self._store_file.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else []
                for item in items:
                    account = Account.from_dict(item)
                    if account.id and account.access_token:
                        self._accounts[account.id] = account
        except Exception:
            pass

    def _save(self) -> None:
        """保存账号到 JSON 文件"""
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        items = [account.to_dict() for account in self._accounts.values()]
        self._store_file.write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # ── 查询 ──────────────────────────────────────────────────────────

    def list_accounts(
        self,
        page: int = 1,
        page_size: int = 50,
        status: str = "",
        search: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """分页查询账号列表，支持筛选和搜索"""
        with self._lock:
            items = [a.to_dict() for a in self._accounts.values()]

        # 状态筛选
        if status:
            items = [a for a in items if a.get("status") == status]

        # 标签筛选
        if tags:
            items = [a for a in items if any(t in (a.get("tags") or []) for t in tags)]

        # 搜索 (邮箱或备注)
        if search:
            s = search.lower()
            items = [a for a in items if s in a.get("email", "").lower() or s in a.get("notes", "").lower()]

        # 按创建时间倒序
        items.sort(key=lambda a: a.get("created_at", ""), reverse=True)

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

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        """获取单个账号"""
        with self._lock:
            account = self._accounts.get(account_id)
            return deepcopy(account.to_dict()) if account else None

    def get_stats(self) -> dict[str, Any]:
        """获取账号统计信息"""
        with self._lock:
            items = list(self._accounts.values())
        total = len(items)
        normal = sum(1 for a in items if a.status in ("normal", "正常"))
        abnormal = sum(1 for a in items if a.status in ("abnormal", "异常"))
        limited = sum(1 for a in items if a.status in ("limited", "限流"))
        disabled = sum(1 for a in items if a.status in ("disabled", "禁用"))
        total_quota = sum(a.quota for a in items if a.status in ("normal", "正常"))
        return {
            "total": total,
            "normal": normal,
            "abnormal": abnormal,
            "limited": limited,
            "disabled": disabled,
            "total_quota": total_quota,
        }

    # ── 增删改 ────────────────────────────────────────────────────────

    def add_accounts(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """批量添加账号（去重：按 email + access_token 判断）"""
        if not items:
            return {"added": 0, "skipped": 0, "items": self.list_accounts()["items"]}

        with self._lock:
            existing_emails = {a.email.lower() for a in self._accounts.values() if a.email}
            existing_tokens = {a.access_token for a in self._accounts.values() if a.access_token}
            added = 0
            skipped = 0

            for item in items:
                email = str(item.get("email") or "").strip().lower()
                token = str(item.get("access_token") or "").strip()
                # 去重检查
                if (email and email in existing_emails) or (token and token in existing_tokens):
                    skipped += 1
                    continue

                account = Account.from_dict({**item, "id": _new_id()})
                self._accounts[account.id] = account
                if email:
                    existing_emails.add(email)
                if token:
                    existing_tokens.add(token)
                added += 1

            if added:
                self._save()

        return {"added": added, "skipped": skipped, "items": self.list_accounts()["items"]}

    def update_account(self, account_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """更新单个账号"""
        with self._lock:
            account = self._accounts.get(account_id)
            if not account:
                return None
            # 合并更新
            current = account.to_dict()
            current.update({k: v for k, v in updates.items() if k != "id"})
            updated = Account.from_dict(current)
            updated.id = account_id
            self._accounts[account_id] = updated
            self._save()
            return deepcopy(updated.to_dict())

    def delete_accounts(self, ids: list[str]) -> dict[str, Any]:
        """批量删除账号"""
        with self._lock:
            removed = 0
            for account_id in ids:
                if account_id in self._accounts:
                    del self._accounts[account_id]
                    removed += 1
            if removed:
                self._save()
        return {"removed": removed, "items": self.list_accounts()["items"]}

    def get_accounts_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """按 ID 批量获取账号"""
        with self._lock:
            return [deepcopy(self._accounts[a_id].to_dict()) for a_id in ids if a_id in self._accounts]

    def import_json(self, accounts: list[dict[str, Any]]) -> dict[str, Any]:
        """从 JSON 数组导入账号（去重）"""
        return self.add_accounts(accounts)

    def export_json(self, ids: list[str] | None = None) -> list[dict[str, Any]]:
        """导出账号为 JSON 数组"""
        with self._lock:
            if ids:
                return [deepcopy(self._accounts[a_id].to_dict()) for a_id in ids if a_id in self._accounts]
            return [deepcopy(a.to_dict()) for a in self._accounts.values()]

    def refresh_account_quota(self, account_id: str) -> dict[str, Any]:
        """刷新单个账号配额和状态 - 调用 OpenAI Backend API"""
        from .backend_api import OpenAIBackendAPI, InvalidAccessTokenError
        from .config_service import config_service

        account = self.get_account(account_id)
        if not account:
            return {"ok": False, "error": "account not found"}

        access_token = str(account.get("access_token") or "").strip()
        if not access_token:
            return {"ok": False, "error": "no access_token"}

        try:
            proxy = config_service.get_proxy()
            api_client = OpenAIBackendAPI(access_token, proxy)
            try:
                info = api_client.get_user_info()
            finally:
                api_client.close()

            # 合并远程信息到本地账号
            updates = {k: v for k, v in info.items() if v is not None and v != ""}
            self.update_account(account_id, updates)
            return {"ok": True, "account_id": account_id, "info": info}

        except InvalidAccessTokenError:
            self.update_account(account_id, {"status": "abnormal", "quota": 0})
            return {"ok": False, "error": "access_token invalid (401)"}
        except Exception as exc:
            self.update_account(account_id, {"status": "abnormal", "quota": 0, "refresh_error": str(exc)[:200]})
            return {"ok": False, "error": str(exc)[:200]}

    def batch_refresh_quotas(self, ids: list[str]) -> dict[str, Any]:
        """批量刷新账号配额 - 使用 ThreadPoolExecutor 并发"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not ids:
            return {"refreshed": 0, "failed": 0, "errors": []}

        max_workers = min(10, len(ids))
        refreshed = 0
        failed = 0
        errors: list[dict[str, str]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.refresh_account_quota, aid): aid for aid in ids}
            for future in as_completed(futures):
                account_id = futures[future]
                try:
                    result = future.result()
                    if result.get("ok"):
                        refreshed += 1
                    else:
                        failed += 1
                        errors.append({"id": account_id, "error": result.get("error", "unknown")})
                except Exception as exc:
                    failed += 1
                    errors.append({"id": account_id, "error": str(exc)})

        return {"refreshed": refreshed, "failed": failed, "errors": errors}


# 全局单例
account_service = AccountService()
