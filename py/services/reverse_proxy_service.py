"""OpenAI 兼容反代和账号池负载均衡。"""

from __future__ import annotations

import json
import random
import time
import uuid
from threading import RLock
from typing import Any

import requests
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .account_service import account_service
from .config_service import config_service
from ..cgpt.image_proxy import chatgpt_image_proxy
from ..cgpt.text_proxy import chatgpt_text_proxy
from .proxy_live_service import proxy_live_service
from .proxy_usage_service import proxy_usage_service
from ..shared.http_client import request_local_retry

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "authorization",
}


class ReverseProxyService:
    """将 `/v1/*` 请求转发到 OpenAI 兼容上游，并用账号池鉴权。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._cursor = 0

    @staticmethod
    def _config() -> dict[str, Any]:
        return config_service.get_reverse_proxy_config()

    @staticmethod
    def _openai_error(message: str, status_code: int, code: str = "proxy_error", extra: dict[str, Any] | None = None) -> JSONResponse:
        error = {"message": message, "type": "proxy_error", "param": None, "code": code}
        if extra:
            error.update(extra)
        return JSONResponse(
            status_code=status_code,
            content={"error": error},
        )

    def _models_response(self) -> dict[str, Any]:
        models = self._config().get("models") or []
        data = []
        for model in models if isinstance(models, list) else []:
            model_id = str(model or "").strip()
            if not model_id:
                continue
            data.append({
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "gpt-web-cf-make",
            })
        return {"object": "list", "data": data}

    @staticmethod
    def _extract_model(body: bytes, content_type: str, query_model: str = "") -> str:
        if query_model:
            return query_model
        if "application/json" not in content_type.lower() or not body:
            return ""
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return ""
        if isinstance(payload, dict):
            return str(payload.get("model") or "")
        return ""

    @staticmethod
    def _is_stream_request(body: bytes, content_type: str, accept: str) -> bool:
        if "text/event-stream" in accept.lower():
            return True
        if "application/json" not in content_type.lower() or not body:
            return False
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return False
        return isinstance(payload, dict) and bool(payload.get("stream"))

    @staticmethod
    def _usage_from_body(content: bytes) -> dict[str, int]:
        try:
            payload = json.loads(content.decode("utf-8"))
        except Exception:
            return {}
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            return {}
        input_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        cached_tokens = int(input_details.get("cached_tokens") or 0) if isinstance(input_details, dict) else 0
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_tokens": cached_tokens,
            "total_tokens": int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
        }

    @staticmethod
    def _stream_preview(chunk: bytes, limit: int = 700) -> str:
        text = chunk.decode("utf-8", errors="ignore")
        text = " ".join(line.strip() for line in text.splitlines() if line.strip())
        if len(text) > limit:
            return text[:limit] + "...[truncated]"
        return text

    @staticmethod
    def _upstream_url(path: str, query_string: bytes) -> str:
        config = config_service.get_reverse_proxy_config()
        base_url = str(config.get("upstream_base_url") or "https://api.openai.com").strip().rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        url = f"{base_url}/{path.strip('/')}" if path else base_url
        if query_string:
            url += "?" + query_string.decode("utf-8", errors="ignore")
        return url

    @staticmethod
    def _request_headers(request: Request, access_token: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in request.headers.items():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            headers[key] = value
        headers["Authorization"] = f"Bearer {access_token}"
        return headers

    @staticmethod
    def _response_headers(upstream_headers: requests.structures.CaseInsensitiveDict[str]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in upstream_headers.items():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            headers[key] = value
        return headers

    def _weighted_candidates(self, model: str) -> list[dict[str, Any]]:
        accounts = account_service.list_proxy_candidates()
        if not accounts:
            return []
        weighted: list[dict[str, Any]] = []
        for account in accounts:
            tags = {str(tag).strip() for tag in account.get("tags") or []}
            if model and tags and any(tag.startswith("model:") for tag in tags):
                if f"model:{model}" not in tags:
                    continue
            quota = int(account.get("quota") or 0)
            weight = max(1, min(20, quota if quota > 0 else 1))
            weighted.extend([account] * weight)
        return weighted or accounts

    def _select_accounts(self, model: str) -> list[dict[str, Any]]:
        candidates = self._weighted_candidates(model)
        if not candidates:
            return []
        strategy = str(self._config().get("strategy") or "round_robin").strip().lower()
        if strategy == "random":
            random.shuffle(candidates)
            return candidates
        with self._lock:
            start = self._cursor % len(candidates)
            self._cursor += 1
        ordered = candidates[start:] + candidates[:start]
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for account in ordered:
            account_id = str(account.get("id") or account.get("access_token") or "")
            if account_id in seen:
                continue
            seen.add(account_id)
            unique.append(account)
        return unique

    @staticmethod
    def _mark_account(account: dict[str, Any], status_code: int, success: bool) -> None:
        account_id = str(account.get("id") or "")
        if not account_id:
            return
        if success:
            account_service.update_account(account_id, {"last_used_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        elif status_code == 429:
            account_service.update_account(account_id, {"status": "limited", "refresh_error": "proxy upstream HTTP 429"})

    @staticmethod
    def _make_attempt(
        account: dict[str, Any] | None,
        status_code: int,
        latency_ms: int,
        success: bool,
        response_bytes: int,
        error: str = "",
    ) -> dict[str, Any]:
        return {
            "account": {
                "id": (account or {}).get("id"),
                "email": (account or {}).get("email"),
            },
            "status_code": status_code,
            "latency_ms": latency_ms,
            "success": success,
            "response_bytes": response_bytes,
            "error": error[:2000],
        }

    @staticmethod
    def _record_usage(entry: dict[str, Any]) -> None:
        proxy_usage_service.record({
            **entry,
            "error": str(entry.get("error") or "")[:2000],
        })

    @staticmethod
    def _record_entry(
        request_id: str,
        api_key: dict[str, Any],
        path: str,
        method: str,
        model: str,
        status_code: int,
        latency_ms: int,
        success: bool,
        request_bytes: int,
        response_bytes: int,
        attempts: list[dict[str, Any]],
        stream: bool = False,
        usage: dict[str, int] | None = None,
        error: str = "",
        request_content: dict[str, Any] | None = None,
        response_content: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "request_id": request_id,
            "api_key": {"id": api_key.get("id"), "name": api_key.get("name")},
            "account": next((attempt.get("account") for attempt in attempts if attempt.get("success")), (attempts[-1].get("account") if attempts else {"id": None, "email": None})),
            "proxy_node_id": next((attempt.get("account", {}).get("proxy_node_id") for attempt in attempts if attempt.get("success")), (attempts[-1].get("account", {}).get("proxy_node_id") if attempts else "")),
            "path": f"/v1/{path.strip('/')}" if path else "/v1",
            "method": method,
            "model": model,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "success": success,
            "stream": stream,
            "request_bytes": request_bytes,
            "response_bytes": response_bytes,
            "usage": usage or {},
            "error": error[:2000],
            "attempts": attempts,
            "attempt_count": len(attempts),
        }
        if request_content:
            entry["_request_content"] = request_content
        if response_content:
            entry["_response_content"] = response_content
        proxy_usage_service.record(entry)

    def _send_upstream(
        self,
        request: Request,
        account: dict[str, Any],
        path: str,
        body: bytes,
        stream: bool,
    ) -> requests.Response:
        timeout = int(self._config().get("timeout_seconds") or 120)
        from ..proxy_pool import proxy_pool_service
        proxy, node_info = proxy_pool_service.resolve_proxy_with_info(proxy_node_id=str(account.get("proxy_node_id") or ""))
        if node_info:
            import logging
            logging.getLogger("proxy").debug(f"[反代] {account.get('email', '?')} → {node_info}")
        proxies = {"http": proxy, "https": proxy} if proxy else None
        return request_local_retry(
            lambda index: requests.request(
                request.method,
                self._upstream_url(path, request.scope.get("query_string") or b""),
                headers=self._request_headers(request, str(account.get("access_token") or "")),
                data=body if body else None,
                timeout=timeout + (10 if index else 0),
                proxies=proxies,
                stream=stream,
            )
        )

    async def proxy(self, request: Request, path: str, api_key: dict[str, Any]) -> Response:
        request_id = uuid.uuid4().hex[:16]
        request_started = time.perf_counter()
        config = self._config()
        if not bool(config.get("enabled", True)):
            return self._openai_error("reverse proxy is disabled", 503, "proxy_disabled")

        body = await request.body()
        content_type = request.headers.get("content-type", "")
        model = self._extract_model(body, content_type, request.query_params.get("model", ""))
        stream = self._is_stream_request(body, content_type, request.headers.get("accept", ""))
        normalized_path = path.strip("/")

        if normalized_path == "images/generations" and request.method.upper() == "POST":
            return await chatgpt_image_proxy.handle_generation(request, api_key, body)

        if normalized_path == "images/edits" and request.method.upper() == "POST":
            return await chatgpt_image_proxy.handle_edit(request, api_key, body)

        if normalized_path == "chat/completions" and request.method.upper() == "POST":
            return await chatgpt_text_proxy.handle_chat_completion(request, api_key, body)

        if normalized_path == "responses" and request.method.upper() == "POST":
            return await chatgpt_text_proxy.handle_response(request, api_key, body)

        if normalized_path == "messages" and request.method.upper() == "POST":
            return await chatgpt_text_proxy.handle_anthropic_message(request, api_key, body)

        proxy_live_service.start(
            request_id=request_id,
            api_key=api_key,
            path=f"/v1/{normalized_path}" if normalized_path else "/v1",
            method=request.method,
            model=model,
            request_bytes=len(body),
            stream=stream,
        )

        if normalized_path == "models" and request.method.upper() == "GET":
            started = time.perf_counter()
            payload = self._models_response()
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._record_entry(
                request_id,
                api_key,
                path,
                request.method,
                "",
                200,
                int((time.perf_counter() - started) * 1000),
                True,
                0,
                len(content),
                [],
            )
            return Response(content=content, media_type="application/json")

        accounts = self._select_accounts(model)
        if not accounts:
            self._record_entry(
                request_id,
                api_key,
                path,
                request.method,
                model,
                503,
                int((time.perf_counter() - request_started) * 1000),
                False,
                len(body),
                0,
                [],
                error="no available upstream account",
            )
            return self._openai_error("no available upstream account", 503, "no_account")

        max_retries = max(1, int(config.get("max_retries") or 2))
        last_error = ""
        attempts: list[dict[str, Any]] = []
        retry_accounts = [accounts[index % len(accounts)] for index in range(max_retries)]
        for index, account in enumerate(retry_accounts):
            started = time.perf_counter()
            upstream: requests.Response | None = None
            try:
                upstream = self._send_upstream(request, account, path, body, stream)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                last_error = str(exc)
                attempts.append(self._make_attempt(account, 0, latency_ms, False, 0, last_error))
                continue

            status_code = int(upstream.status_code)
            should_retry = status_code in {401, 429, 500, 502, 503, 504}
            if should_retry:
                error_body = upstream.text[:2000]
                response_bytes = len(error_body.encode("utf-8", errors="ignore"))
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._mark_account(account, status_code, False)
                attempts.append(self._make_attempt(account, status_code, latency_ms, False, response_bytes, error_body))
                upstream.close()
                last_error = error_body
                if index >= max_retries - 1:
                    total_latency_ms = int((time.perf_counter() - request_started) * 1000)
                    self._record_entry(
                        request_id,
                        api_key,
                        path,
                        request.method,
                        model,
                        502,
                        total_latency_ms,
                        False,
                        len(body),
                        response_bytes,
                        attempts,
                        stream=stream,
                        error=last_error or f"upstream failed with HTTP {status_code}",
                    )
                    return self._openai_error(
                        f"all upstream attempts failed; last upstream status {status_code}",
                        502,
                        "upstream_error",
                        {"upstream_status": status_code, "attempt_count": len(attempts)},
                    )
                continue

            if stream:
                return self._stream_response(upstream, request_id, api_key, account, path, request.method, model, len(body), request_started, attempts)
            return self._buffered_response(upstream, request_id, api_key, account, path, request.method, model, len(body), request_started, attempts)

        total_latency_ms = int((time.perf_counter() - request_started) * 1000)
        self._record_entry(
            request_id,
            api_key,
            path,
            request.method,
            model,
            502,
            total_latency_ms,
            False,
            len(body),
            0,
            attempts,
            stream=stream,
            error=last_error or "upstream request failed",
        )
        return self._openai_error(last_error or "upstream request failed", 502, "upstream_error")

    def _buffered_response(
        self,
        upstream: requests.Response,
        request_id: str,
        api_key: dict[str, Any],
        account: dict[str, Any],
        path: str,
        method: str,
        model: str,
        request_bytes: int,
        request_started: float,
        attempts: list[dict[str, Any]],
    ) -> Response:
        content = upstream.content
        latency_ms = int((time.perf_counter() - request_started) * 1000)
        success = 200 <= upstream.status_code < 400
        self._mark_account(account, int(upstream.status_code), success)
        attempts.append(self._make_attempt(
            account,
            int(upstream.status_code),
            latency_ms,
            success,
            len(content),
            "" if success else content.decode("utf-8", errors="ignore")[:2000],
        ))
        self._record_entry(
            request_id,
            api_key,
            path,
            method,
            model,
            int(upstream.status_code),
            latency_ms,
            success,
            request_bytes,
            len(content),
            attempts,
            stream=False,
            usage=self._usage_from_body(content),
            error="" if success else content.decode("utf-8", errors="ignore")[:2000],
        )
        return Response(
            content=content,
            status_code=int(upstream.status_code),
            headers=self._response_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )

    def _stream_response(
        self,
        upstream: requests.Response,
        request_id: str,
        api_key: dict[str, Any],
        account: dict[str, Any],
        path: str,
        method: str,
        model: str,
        request_bytes: int,
        request_started: float,
        attempts: list[dict[str, Any]],
    ) -> StreamingResponse:
        response_bytes = 0
        chunk_count = 0

        def iterator():
            nonlocal response_bytes, chunk_count
            proxy_live_service.log(request_id, "upstream stream opened")
            try:
                for chunk in upstream.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                    chunk_count += 1
                    response_bytes += len(chunk)
                    preview = self._stream_preview(chunk)
                    if chunk_count <= 5 or chunk_count % 20 == 0:
                        proxy_live_service.log(request_id, f"upstream stream chunk {chunk_count}: {preview}")
                    proxy_live_service.update(
                        request_id,
                        {
                            "stream": True,
                            "stream_chunks": chunk_count,
                            "response_bytes": response_bytes,
                            "latency_ms": int((time.perf_counter() - request_started) * 1000),
                            "attempts": attempts,
                            "attempt_count": len(attempts),
                        },
                        stream_log=f"#{chunk_count} {preview}",
                    )
                    yield chunk
            finally:
                latency_ms = int((time.perf_counter() - request_started) * 1000)
                success = 200 <= upstream.status_code < 400
                self._mark_account(account, int(upstream.status_code), success)
                attempts.append(self._make_attempt(
                    account,
                    int(upstream.status_code),
                    latency_ms,
                    success,
                    response_bytes,
                    "" if success else "stream upstream error",
                ))
                self._record_entry(
                    request_id,
                    api_key,
                    path,
                    method,
                    model,
                    int(upstream.status_code),
                    latency_ms,
                    success,
                    request_bytes,
                    response_bytes,
                    attempts,
                    stream=True,
                    error="" if success else "stream upstream error",
                )
                upstream.close()

        headers = self._response_headers(upstream.headers)
        headers.setdefault("Cache-Control", "no-cache")
        headers.setdefault("X-Accel-Buffering", "no")
        headers["Transfer-Encoding"] = "identity"
        return StreamingResponse(
            iterator(),
            status_code=int(upstream.status_code),
            headers=headers,
            media_type=upstream.headers.get("content-type"),
        )


reverse_proxy_service = ReverseProxyService()
