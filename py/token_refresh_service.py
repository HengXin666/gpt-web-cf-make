"""Token 保活服务 - 使用 refresh_token 批量续期 access_token"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from .config_service import config_service
from .account_service import account_service
from .register.oauth import refresh_token, decode_jwt_payload
from .shared.http_client import is_local_retryable_error, local_retryable_message
from .shared.models import _now


def _anonymize(text: str) -> str:
    """脱敏显示 token"""
    if not text:
        return "(empty)"
    return text[:12] + "..." + text[-8:] if len(text) > 24 else text


class TokenRefreshService:
    """Token 刷新服务 - 管理批量 refresh_token 续期"""

    def __init__(self):
        self._lock = RLock()

    def refresh_single(self, account_id: str) -> dict[str, Any]:
        """刷新单个账号的 access_token"""
        account = account_service.get_account(account_id)
        if not account:
            return {"ok": False, "error": "account not found"}

        r_token = str(account.get("refresh_token") or "").strip()
        if not r_token:
            return {"ok": False, "error": "no refresh_token"}

        config = config_service.get()
        from .proxy_pool import proxy_pool_service
        proxy, node_info = proxy_pool_service.resolve_proxy_with_info(proxy_node_id=str(account.get("proxy_node_id") or ""))
        if node_info:
            print(f"[token-refresh] {account.get('email', account_id)} → 代理节点: {node_info}")
        profile = str(account.get("oauth_profile") or config.get("oauth_profile") or "platform")
        oauth = config_service.get_oauth(profile)
        client_id = str(account.get("oauth_client_id") or oauth.get("client_id") or "")
        scope = str(account.get("oauth_scope") or oauth.get("scope") or "openid profile email")

        max_attempts = 3
        result: dict[str, Any] = {}
        for attempt in range(1, max_attempts + 1):
            try:
                result = refresh_token(
                    oauth=oauth,
                    refresh_token_value=r_token,
                    client_id=client_id,
                    scope=scope,
                    proxy=proxy,
                )
                if not result.get("ok") or result.get("status_code") != 200:
                    body = result.get("body", {})
                    error_msg = str(body.get("error_description") or body.get("error") or json.dumps(body)[:200])
                    if is_local_retryable_error(error_msg):
                        if attempt < max_attempts:
                            continue
                        error_msg = local_retryable_message(error_msg, max_attempts)
                        account_service.update_account(account_id, {
                            "refresh_error": error_msg,
                            "last_refreshed_at": _now(),
                        })
                        return {"ok": False, "error": error_msg, "error_group": "本地网络或代理错误", "retryable": True}
                break
            except Exception as exc:
                if is_local_retryable_error(exc):
                    if attempt < max_attempts:
                        continue
                    error_msg = local_retryable_message(exc, max_attempts)
                    account_service.update_account(account_id, {
                        "refresh_error": error_msg,
                        "last_refreshed_at": _now(),
                    })
                    return {"ok": False, "error": error_msg, "error_group": "本地网络或代理错误", "retryable": True}
                error_msg = str(exc)
                account_service.update_account(account_id, {
                    "status": "abnormal",
                    "refresh_error": error_msg,
                    "last_refreshed_at": _now(),
                })
                return {"ok": False, "error": error_msg, "error_group": "Token 刷新异常", "retryable": False}

        if not result.get("ok") or result.get("status_code") != 200:
            body = result.get("body", {})
            error_msg = str(body.get("error_description") or body.get("error") or json.dumps(body)[:200])
            # 检测 refresh_token_reused 错误
            if "refresh_token_reused" in error_msg or "invalid_grant" in error_msg:
                account_service.update_account(account_id, {
                    "status": "abnormal",
                    "refresh_error": error_msg,
                    "last_refreshed_at": _now(),
                })
                return {"ok": False, "error": error_msg, "error_group": "refresh_token invalid/reused", "retryable": False}
            account_service.update_account(account_id, {
                "refresh_error": error_msg,
                "last_refreshed_at": _now(),
            })
            return {"ok": False, "error": error_msg, "error_group": "Token 刷新失败", "retryable": False}

        body = result.get("body", {})
        new_access_token = str(body.get("access_token") or "").strip()
        new_refresh_token = str(body.get("refresh_token") or "").strip()
        new_id_token = str(body.get("id_token") or "").strip()

        if not new_access_token:
            return {"ok": False, "error": "no access_token in refresh response"}

        # 解码新 token 获取信息
        claims = decode_jwt_payload(new_id_token or new_access_token)
        auth_claims = claims.get("https://api.openai.com/auth") or {}
        profile_claims = claims.get("https://api.openai.com/profile") or {}

        account_service.update_account(account_id, {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token or r_token,
            "id_token": new_id_token or account.get("id_token", ""),
            "status": "normal",
            "refresh_error": "",
            "last_refreshed_at": _now(),
            "plan_type": auth_claims.get("chatgpt_plan_type", account.get("plan_type", "free")),
            "email": profile_claims.get("email") or account.get("email", ""),
        })
        return {"ok": True, "account_id": account_id}

    def batch_refresh(self, ids: list[str]) -> dict[str, Any]:
        """批量刷新 Token - 支持缩减重试（仅重试失败项）"""
        if not ids:
            return {"refreshed": 0, "failed": 0, "errors": []}

        config = config_service.get_token_refresh_config()
        max_workers = min(int(config.get("max_workers") or 10), len(ids))
        refreshed = 0
        failed = 0
        errors: list[dict[str, str]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.refresh_single, account_id): account_id for account_id in ids}
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

    def renew_expiring(self, expiring_days: int = 5) -> dict[str, Any]:
        """续期所有即将过期的 Token（在N天内过期）"""
        all_accounts = account_service.list_accounts(page=1, page_size=10000)["items"]
        expiring_ids: list[str] = []

        for account in all_accounts:
            a_token = str(account.get("access_token") or "")
            if not a_token:
                continue
            claims = decode_jwt_payload(a_token)
            exp = claims.get("exp")
            if not exp:
                continue
            try:
                exp_time = datetime.fromtimestamp(int(exp), tz=timezone.utc)
                remaining = (exp_time - datetime.now(timezone.utc)).total_seconds()
                if remaining <= expiring_days * 86400:
                    expiring_ids.append(account["id"])
            except Exception:
                continue

        if not expiring_ids:
            return {"refreshed": 0, "failed": 0, "errors": [], "expiring_count": 0}

        result = self.batch_refresh(expiring_ids)
        result["expiring_count"] = len(expiring_ids)
        return result

    def get_token_stats(self) -> dict[str, Any]:
        """获取 Token 健康统计"""
        all_accounts = account_service.list_accounts(page=1, page_size=10000)["items"]
        valid = 0
        expiring_soon = 0
        expired = 0
        no_token = 0

        for account in all_accounts:
            a_token = str(account.get("access_token") or "")
            r_token = str(account.get("refresh_token") or "")
            if not a_token or not r_token:
                no_token += 1
                continue
            claims = decode_jwt_payload(a_token)
            exp = claims.get("exp")
            if not exp:
                valid += 1
                continue
            try:
                exp_time = datetime.fromtimestamp(int(exp), tz=timezone.utc)
                remaining = (exp_time - datetime.now(timezone.utc)).total_seconds()
                if remaining <= 0:
                    expired += 1
                elif remaining <= 5 * 86400:
                    expiring_soon += 1
                else:
                    valid += 1
            except Exception:
                valid += 1

        return {
            "total": len(all_accounts),
            "valid": valid,
            "expiring_soon": expiring_soon,
            "expired": expired,
            "no_token": no_token,
            "abnormal": sum(1 for a in all_accounts if a.get("status") == "abnormal"),
        }


# 全局单例
token_refresh_service = TokenRefreshService()
