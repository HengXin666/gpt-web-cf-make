"""HTTP 客户端工具 - 提供统一的请求接口和错误处理"""

from __future__ import annotations

from typing import Any


LOCAL_RETRY_ATTEMPTS = 5
LOCAL_RETRY_DELAY_SECONDS = 1.0
LOCAL_RETRYABLE_ERROR_KEYWORDS = (
    "curl:",
    "failed to perform",
    "connection closed",
    "connection reset",
    "connection refused",
    "connection aborted",
    "remote end closed",
    "empty reply",
    "timed out",
    "timeout",
    "temporary failure",
    "name or service not known",
    "proxy",
    "tls",
    "ssl",
    "eof",
)


class UpstreamError(RuntimeError):
    """上游请求错误"""
    def __init__(self, message: str, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def is_local_retryable_error(error: object) -> bool:
    text = str(error or "").lower()
    return any(keyword in text for keyword in LOCAL_RETRYABLE_ERROR_KEYWORDS)


def is_timeout_error(error: object) -> bool:
    text = str(error or "").lower()
    return "timed out" in text or "timeout" in text or "超时" in text


def local_retryable_message(error: object, attempts: int) -> str:
    detail = str(error or "local request failed")
    return f"本地网络或代理错误，已自动重试 {attempts} 次后仍失败：{detail}"


def _retry_timeout(timeout: Any) -> Any:
    if isinstance(timeout, (int, float)):
        return timeout + 10
    if isinstance(timeout, tuple):
        return tuple((item + 10 if isinstance(item, (int, float)) else item) for item in timeout)
    return timeout


def install_local_retry(session: Any, attempts: int = LOCAL_RETRY_ATTEMPTS, delay_seconds: float = LOCAL_RETRY_DELAY_SECONDS) -> Any:
    """让 curl_cffi Session 在本地代理/curl 连接错误时静默原地重试。"""
    import time

    if getattr(session, "_local_retry_installed", False):
        return session
    raw_request = session.request

    def request(*args: Any, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        original_timeout = kwargs.get("timeout")
        for index in range(max(1, attempts)):
            if index > 0:
                time.sleep(delay_seconds)
                if original_timeout is not None:
                    kwargs["timeout"] = _retry_timeout(original_timeout)
            try:
                return raw_request(*args, **kwargs)
            except Exception as exc:
                if not is_local_retryable_error(exc) or index >= attempts - 1:
                    raise
                last_error = exc
        if last_error:
            raise last_error
        return raw_request(*args, **kwargs)

    session.request = request
    session._local_retry_installed = True
    return session


def request_local_retry(call, attempts: int = LOCAL_RETRY_ATTEMPTS, delay_seconds: float = LOCAL_RETRY_DELAY_SECONDS) -> Any:
    """对 requests/curl_cffi 的一次性调用做本地错误静默重试。"""
    import time

    last_error: Exception | None = None
    for index in range(max(1, attempts)):
        if index > 0:
            time.sleep(delay_seconds)
        try:
            return call(index)
        except Exception as exc:
            if not is_local_retryable_error(exc) or index >= attempts - 1:
                raise
            last_error = exc
    if last_error:
        raise last_error
    return call(0)


def create_session(proxy: str = "") -> Any:
    """创建带指纹伪装的 curl_cffi Session"""
    from curl_cffi import requests as curl_requests
    session: Any = curl_requests.Session(impersonate="chrome", http_version=get_curl_http_version())
    session.verify = False
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return install_local_retry(session)


def get_curl_http_version() -> Any:
    """将配置转换为 curl_cffi 的 HTTP 版本枚举。"""
    from curl_cffi.const import CurlHttpVersion
    from ..config_service import config_service

    return CurlHttpVersion.V1_1 if config_service.get_http_version() == "http1.1" else CurlHttpVersion.V2_0


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
    attempts = 1 if getattr(session, "_local_retry_installed", False) else max(1, max(retry_attempts, LOCAL_RETRY_ATTEMPTS))
    for index in range(attempts):
        try:
            return session.request(method.upper(), url, timeout=timeout + (10 if index else 0), **kwargs), ""
        except Exception as error:
            if not is_local_retryable_error(error):
                return None, str(error)
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
