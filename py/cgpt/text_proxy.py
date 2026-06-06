"""ChatGPT Web backend backed OpenAI text endpoints."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from .helper import anthropic_sse_stream, sse_json_stream
from .pool import account_service
from .protocol import anthropic_v1_messages, openai_v1_chat_complete, openai_v1_response
from .protocol.conversation import count_text_tokens
from ..services.proxy_live_service import proxy_live_service
from ..services.proxy_usage_service import proxy_usage_service


def _openai_error(message: str, status_code: int = 502, code: str = "upstream_error", error_type: str = "server_error") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": None, "code": code}},
    )


def _usage_from_result(result: Any) -> dict[str, int]:
    if not isinstance(result, dict):
        return {}
    usage = result.get("usage")
    if isinstance(usage, dict):
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
        }
    return {}


def _attempt_error(attempts: list[dict[str, Any]], fallback: str) -> str:
    for attempt in reversed(attempts):
        error = str(attempt.get("error") or "").strip()
        if error and error != "selected":
            return error
    return fallback


def _stream_preview(chunk: str | bytes, limit: int = 700) -> str:
    text = chunk.decode("utf-8", errors="ignore") if isinstance(chunk, bytes) else str(chunk)
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) > limit:
        return text[:limit] + "...[truncated]"
    return text


def _extract_stream_text(chunk: str, stream_kind: str) -> str:
    for line in str(chunk or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except Exception:
            continue
        if stream_kind == "anthropic":
            delta = payload.get("delta") if isinstance(payload, dict) else {}
            return str(delta.get("text") or "") if isinstance(delta, dict) else ""
        if isinstance(payload, dict) and payload.get("type") == "response.output_text.delta":
            return str(payload.get("delta") or "")
        choices = payload.get("choices") if isinstance(payload, dict) else None
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
        return str(delta.get("content") or "")
    return ""


def _request_usage(body: dict[str, Any], model: str, output_text: str) -> dict[str, int]:
    prompt_source = body.get("messages") or body.get("input") or body.get("prompt") or ""
    try:
        prompt_text = json.dumps(prompt_source, ensure_ascii=False)
    except Exception:
        prompt_text = str(prompt_source)
    prompt_tokens = count_text_tokens(prompt_text, model)
    completion_tokens = count_text_tokens(output_text, model)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


class ChatGPTTextProxy:
    async def handle_chat_completion(self, request: Request, api_key: dict[str, Any], body_bytes: bytes) -> JSONResponse | StreamingResponse:
        return await self._handle_json(
            request=request,
            api_key=api_key,
            body_bytes=body_bytes,
            path="/v1/chat/completions",
            call=openai_v1_chat_complete.handle,
            stream_kind="openai",
        )

    async def handle_response(self, request: Request, api_key: dict[str, Any], body_bytes: bytes) -> JSONResponse | StreamingResponse:
        return await self._handle_json(
            request=request,
            api_key=api_key,
            body_bytes=body_bytes,
            path="/v1/responses",
            call=openai_v1_response.handle,
            stream_kind="openai",
        )

    async def handle_anthropic_message(self, request: Request, api_key: dict[str, Any], body_bytes: bytes) -> JSONResponse | StreamingResponse:
        return await self._handle_json(
            request=request,
            api_key=api_key,
            body_bytes=body_bytes,
            path="/v1/messages",
            call=anthropic_v1_messages.handle,
            stream_kind="anthropic",
        )

    async def _handle_json(
        self,
        *,
        request: Request,
        api_key: dict[str, Any],
        body_bytes: bytes,
        path: str,
        call,
        stream_kind: str,
    ) -> JSONResponse | StreamingResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:16]
        try:
            body = await request.json()
        except Exception as exc:
            return _openai_error(f"invalid JSON body: {exc}", 400, "invalid_request", "invalid_request_error")
        if not isinstance(body, dict):
            return _openai_error("JSON body must be an object", 400, "invalid_request", "invalid_request_error")
        model = str(body.get("model") or "auto")
        # 提取用户消息文本用于实时展示
        req_text = ""
        if isinstance(body.get("messages"), list):
            for msg in reversed(body["messages"]):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    txt = msg.get("content")
                    if isinstance(txt, str):
                        req_text = txt
                    elif isinstance(txt, list):
                        req_text = " ".join(str(p.get("text") or "") for p in txt if isinstance(p, dict) and p.get("type") == "text")
                    break
        if not req_text and isinstance(body.get("prompt"), str):
            req_text = body["prompt"]
        proxy_live_service.start(
            request_id=request_id,
            api_key=api_key,
            path=path,
            method=request.method,
            model=model,
            request_bytes=len(body_bytes),
            stream=bool(body.get("stream")),
            request_text=req_text,
        )
        tracking_token = account_service.start_attempt_tracking()
        try:
            result = await run_in_threadpool(lambda: call(body))
            if body.get("stream"):
                attempts = account_service.current_attempts()
                account_service.stop_attempt_tracking(tracking_token)
                proxy_live_service.update(request_id, {"stream": True, "attempts": attempts, "attempt_count": len(attempts)})
                return self._stream_response(request_id, api_key, path, request.method, model, len(body_bytes), started, result, attempts, stream_kind, body)

            attempts = account_service.stop_attempt_tracking(tracking_token)
            content = json.dumps(result, ensure_ascii=False).encode("utf-8")
            latency_ms = int((time.perf_counter() - started) * 1000)
            # 提取请求文本（最后一条用户消息）
            req_text = ""
            if isinstance(body.get("messages"), list):
                for msg in reversed(body["messages"]):
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        txt = msg.get("content")
                        if isinstance(txt, str):
                            req_text = txt[:20000]
                        elif isinstance(txt, list):
                            # 多模态内容
                            parts = []
                            for part in txt:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    parts.append(str(part.get("text") or ""))
                            req_text = " ".join(parts)[:20000]
                        break
            # 提取响应文本
            resp_text = ""
            if isinstance(result.get("choices"), list) and result["choices"]:
                choice = result["choices"][0]
                if isinstance(choice, dict):
                    msg = choice.get("message") or choice.get("delta") or {}
                    resp_text = str(msg.get("content") or "")[:20000]
            # 处理 content 字段（兼容其他格式）
            if not resp_text and isinstance(result.get("content"), str):
                resp_text = result["content"][:3000]
            if not req_text and isinstance(body.get("prompt"), str):
                req_text = body["prompt"][:3000]
            self._record(
                request_id, api_key, path, request.method, model, 200, latency_ms, True, len(body_bytes), len(content),
                attempts, stream=False, usage=_usage_from_result(result),
                request_content={"text": req_text},
                response_content={"text": resp_text},
            )
            return JSONResponse(content=result)
        except HTTPException as exc:
            attempts = account_service.stop_attempt_tracking(tracking_token)
            detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
            content = json.dumps(detail, ensure_ascii=False).encode("utf-8")
            self._record(request_id, api_key, path, request.method, model, int(exc.status_code), int((time.perf_counter() - started) * 1000), False, len(body_bytes), len(content), attempts, stream=bool(body.get("stream")), error=str(detail)[:2000])
            return JSONResponse(status_code=int(exc.status_code), content=detail)
        except Exception as exc:
            attempts = account_service.stop_attempt_tracking(tracking_token)
            latency_ms = int((time.perf_counter() - started) * 1000)
            error = _attempt_error(attempts, str(exc))
            self._record(request_id, api_key, path, request.method, model, 502, latency_ms, False, len(body_bytes), len(error.encode("utf-8")), attempts, stream=bool(body.get("stream")), error=error)
            return _openai_error(error)

    def _stream_response(
        self,
        request_id: str,
        api_key: dict[str, Any],
        path: str,
        method: str,
        model: str,
        request_bytes: int,
        started: float,
        result,
        attempts: list[dict[str, Any]],
        stream_kind: str,
        body: dict[str, Any],
    ) -> StreamingResponse:
        response_bytes = 0
        chunk_count = 0
        stream_error = ""
        output_parts: list[str] = []
        stream_factory = anthropic_sse_stream if stream_kind == "anthropic" else sse_json_stream

        def tracked_items():
            nonlocal stream_error
            token = account_service.bind_attempt_tracking(attempts)
            try:
                yield from result
            except Exception as exc:
                stream_error = str(exc)
                raise
            finally:
                account_service.stop_attempt_tracking(token)

        def iterator():
            nonlocal response_bytes, chunk_count
            proxy_live_service.log(request_id, "stream opened")
            try:
                for chunk in stream_factory(tracked_items()):
                    encoded = chunk.encode("utf-8")
                    chunk_count += 1
                    response_bytes += len(encoded)
                    text_delta = _extract_stream_text(chunk, stream_kind)
                    if text_delta:
                        output_parts.append(text_delta)
                    preview = _stream_preview(chunk)
                    if chunk_count <= 5 or chunk_count % 20 == 0:
                        proxy_live_service.log(request_id, f"stream chunk {chunk_count}: {preview}")
                    proxy_live_service.update(
                        request_id,
                        {
                            "stream": True,
                            "stream_chunks": chunk_count,
                            "response_bytes": response_bytes,
                            "latency_ms": int((time.perf_counter() - started) * 1000),
                            "attempts": attempts,
                            "attempt_count": len(attempts),
                        },
                        stream_log=f"#{chunk_count} {preview}",
                    )
                    yield encoded
            finally:
                success = not stream_error
                self._record(
                    request_id,
                    api_key,
                    path,
                    method,
                    model,
                    200,
                    int((time.perf_counter() - started) * 1000),
                    success,
                    request_bytes,
                    response_bytes,
                    attempts,
                    stream=True,
                    usage=_request_usage(body, model, "".join(output_parts)),
                    error=stream_error,
                )

        return StreamingResponse(
            iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Transfer-Encoding": "identity",
            },
        )

    @staticmethod
    def _record(
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
            "path": path,
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


chatgpt_text_proxy = ChatGPTTextProxy()
