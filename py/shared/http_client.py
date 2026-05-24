"""HTTP 客户端工具 - 提供统一的请求接口和错误处理"""

from __future__ import annotations

from typing import Any


class UpstreamError(RuntimeError):
    """上游请求错误"""
    def __init__(self, message: str, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def create_session(proxy: str = "") -> Any:
    """创建带指纹伪装的 curl_cffi Session"""
    from curl_cffi import requests as curl_requests
    session: Any = curl_requests.Session(impersonate="chrome")
    session.verify = False
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


def request_with_retry(
    session: Any,
    method: str,
    url: str,
    retry_attempts: int = 3,
    timeout: int = 30,
    **kwargs: Any,
) -> tuple[Any | None, str]:
    """带重试的 HTTP 请求"""
    import time
    last_error = ""
    for _ in range(max(1, retry_attempts)):
        try:
            return session.request(method.upper(), url, timeout=timeout, **kwargs), ""
        except Exception as error:
            last_error = str(error)
            time.sleep(1)
    return None, last_error


def response_json(resp: Any) -> dict[str, Any]:
    """安全获取 JSON 响应体"""
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
