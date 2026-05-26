"""OpenAI Backend API 客户端 - 获取账号状态、配额、计划类型等远程信息"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import urllib3
from curl_cffi import requests
from .shared.http_client import get_curl_http_version, install_local_retry

urllib3.disable_warnings()


class InvalidAccessTokenError(RuntimeError):
    """access_token 无效（401）"""
    pass


class UpstreamHTTPError(RuntimeError):
    """上游请求失败"""
    def __init__(self, context: str, status_code: int, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(f"{context} failed: HTTP {status_code}")


def _ensure_ok(response, context: str) -> None:
    """检查 HTTP 响应状态码"""
    if 200 <= response.status_code < 300:
        return
    if response.status_code == 401:
        raise InvalidAccessTokenError(f"{context}: HTTP 401")
    raise UpstreamHTTPError(context, response.status_code, str(response.text)[:300])


class OpenAIBackendAPI:
    """OpenAI ChatGPT 后端 API 客户端 - 并发获取用户信息/配额/计划"""

    BASE_URL = "https://chatgpt.com"

    def __init__(self, access_token: str, proxy: str = ""):
        if not access_token:
            raise RuntimeError("access_token is required")
        self.access_token = access_token
        self.device_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())

        self.session = install_local_retry(requests.Session(impersonate="edge101", http_version=get_curl_http_version()))
        self.session.verify = False
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/143.0.0.0 Safari/537.36",
            "Origin": self.BASE_URL,
            "Referer": self.BASE_URL + "/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "OAI-Device-Id": self.device_id,
            "OAI-Session-Id": self.session_id,
            "OAI-Language": "zh-CN",
            "Authorization": f"Bearer {self.access_token}",
        })

    def _headers(self, path: str, extra: dict | None = None) -> dict[str, str]:
        headers = dict(self.session.headers)
        headers["X-OpenAI-Target-Path"] = path
        headers["X-OpenAI-Target-Route"] = path
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _extract_quota(limits_progress: list) -> tuple[int, str | None, bool]:
        for item in limits_progress:
            if isinstance(item, dict) and item.get("feature_name") == "image_gen":
                remaining = int(item.get("remaining") or 0)
                reset_after = str(item.get("reset_after") or "") or None
                return remaining, reset_after, False
        return 0, None, True

    def _get_me(self) -> dict[str, Any]:
        path = "/backend-api/me"
        resp = self.session.get(self.BASE_URL + path, headers=self._headers(path), timeout=20)
        if resp.status_code == 401:
            raise InvalidAccessTokenError(f"{path}: HTTP 401")
        _ensure_ok(resp, path)
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def _get_conversation_init(self) -> dict[str, Any]:
        path = "/backend-api/conversation/init"
        resp = self.session.post(
            self.BASE_URL + path,
            headers=self._headers(path, {"Content-Type": "application/json"}),
            json={"gizmo_id": None, "requested_default_model": None, "conversation_id": None, "timezone_offset_min": -480},
            timeout=20,
        )
        if resp.status_code == 401:
            raise InvalidAccessTokenError(f"{path}: HTTP 401")
        _ensure_ok(resp, path)
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def _get_default_account(self) -> dict[str, Any]:
        path = "/backend-api/accounts/check/v4-2023-04-27"
        resp = self.session.get(
            self.BASE_URL + path + "?timezone_offset_min=-480",
            headers=self._headers(path),
            timeout=20,
        )
        if resp.status_code == 401:
            raise InvalidAccessTokenError(f"{path}: HTTP 401")
        _ensure_ok(resp, path)
        payload = resp.json()
        if not isinstance(payload, dict):
            return {}
        return ((payload.get("accounts") or {}).get("default") or {}).get("account") or {}

    def get_user_info(self) -> dict[str, Any]:
        """并发获取用户信息、配额、计划类型"""
        with ThreadPoolExecutor(max_workers=3) as executor:
            me_future = executor.submit(self._get_me)
            init_future = executor.submit(self._get_conversation_init)
            account_future = executor.submit(self._get_default_account)
            me_data = me_future.result()
            init_data = init_future.result()
            account_data = account_future.result()

        plan_type = str(account_data.get("plan_type") or "free")
        limits_progress = init_data.get("limits_progress")
        limits_progress = limits_progress if isinstance(limits_progress, list) else []
        quota, restore_at, image_quota_unknown = self._extract_quota(limits_progress)

        if image_quota_unknown and plan_type.lower() != "free":
            status = "normal"
        elif quota == 0 and not image_quota_unknown:
            status = "limited"
        else:
            status = "normal"

        return {
            "email": me_data.get("email"),
            "user_id": me_data.get("id"),
            "plan_type": plan_type,
            "quota": quota,
            "image_quota_unknown": image_quota_unknown,
            "limits_progress": limits_progress,
            "default_model_slug": init_data.get("default_model_slug"),
            "quota_reset_at": restore_at or "",
            "status": status,
        }

    def close(self) -> None:
        self.session.close()
