"""把本项目账号池适配成 chatgpt2api 所需接口。"""

from __future__ import annotations

import contextvars
from threading import RLock
from typing import Any

from ..account_service import account_service as base_account_service
from ..shared.models import _now


class AdapterAccountService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._cursor = 0
        self._attempts_var: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("cgpt_attempts", default=None)

    def start_attempt_tracking(self):
        attempts: list[dict[str, Any]] = []
        self._attempts_var.set(attempts)
        return attempts

    def current_attempts(self) -> list[dict[str, Any]]:
        attempts = self._attempts_var.get()
        return attempts if attempts is not None else []

    def bind_attempt_tracking(self, attempts: list[dict[str, Any]]):
        self._attempts_var.set(attempts)
        return attempts

    def stop_attempt_tracking(self, tracking) -> list[dict[str, Any]]:
        attempts = self._attempts_var.get() or tracking or []
        self._attempts_var.set(None)
        return attempts

    def _append_attempt(self, account: dict[str, Any], event: str = "selected") -> None:
        attempts = self._attempts_var.get()
        if attempts is None:
            return
        attempts.append({
            "account": {"id": account.get("id"), "email": account.get("email")},
            "status_code": 0,
            "latency_ms": 0,
            "success": False,
            "response_bytes": 0,
            "error": event,
        })

    def _finish_attempt(self, access_token: str, success: bool, error: str = "") -> None:
        attempts = self._attempts_var.get()
        if attempts is None:
            return
        account = self.get_account(access_token)
        account_id = account.get("id")
        for attempt in reversed(attempts):
            if (attempt.get("account") or {}).get("id") == account_id:
                attempt["success"] = success
                attempt["status_code"] = 200 if success else 0
                attempt["error"] = "" if success else (error or attempt.get("error") or "failed")
                return

    def _candidates(self, attempted_tokens: set[str] | None = None) -> list[dict[str, Any]]:
        attempted_tokens = attempted_tokens or set()
        items = []
        for item in base_account_service.list_proxy_candidates():
            token = str(item.get("access_token") or "").strip()
            if not token or token in attempted_tokens:
                continue
            items.append(item)
        return items

    def get_account(self, access_token: str) -> dict[str, Any]:
        token = str(access_token or "").strip()
        if not token:
            return {}
        for item in base_account_service.export_json():
            if str(item.get("access_token") or "").strip() == token:
                return item
        return {}

    def get_available_access_token(self, attempted_tokens: set[str] | None = None) -> str:
        candidates = self._candidates(attempted_tokens)
        if not candidates:
            raise RuntimeError("no available image account")
        with self._lock:
            index = self._cursor % len(candidates)
            self._cursor += 1
        account = candidates[index]
        self._append_attempt(account)
        return str(account.get("access_token") or "")

    def get_text_access_token(self, attempted_tokens: set[str] | None = None) -> str:
        return self.get_available_access_token(attempted_tokens)

    def mark_image_result(self, access_token: str, success: bool) -> None:
        account = self.get_account(access_token)
        account_id = str(account.get("id") or "")
        if not account_id:
            return
        self._finish_attempt(access_token, success, "" if success else "image request failed")
        updates: dict[str, Any] = {"last_used_at": _now()}
        if not success:
            updates["refresh_error"] = "last image request failed"
        base_account_service.update_account(account_id, updates)

    def mark_text_used(self, access_token: str) -> None:
        account = self.get_account(access_token)
        account_id = str(account.get("id") or "")
        if account_id:
            self._finish_attempt(access_token, True)
            base_account_service.update_account(account_id, {"last_used_at": _now()})

    def remove_invalid_token(self, access_token: str, reason: str = "") -> None:
        account = self.get_account(access_token)
        account_id = str(account.get("id") or "")
        if account_id:
            self._finish_attempt(access_token, False, reason or "invalid token")
            base_account_service.update_account(account_id, {"status": "abnormal", "refresh_error": reason or "invalid token"})


account_service = AdapterAccountService()
