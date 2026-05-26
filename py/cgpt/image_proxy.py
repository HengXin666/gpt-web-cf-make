"""ChatGPT Web backend backed OpenAI image endpoints."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from .api.image_inputs import parse_image_edit_request, read_image_sources
from .helper import sse_json_stream
from .pool import account_service
from .protocol import openai_v1_image_edit, openai_v1_image_generations
from .protocol.conversation import ImageGenerationError, count_text_tokens
from ..proxy_live_service import proxy_live_service
from ..proxy_pricing_service import DEFAULT_IMAGE_INPUT_TOKENS, DEFAULT_IMAGE_OUTPUT_TOKENS
from ..proxy_usage_service import proxy_usage_service


def _openai_error(message: str, status_code: int = 502, code: str = "upstream_error", error_type: str = "server_error") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": None, "code": code}},
    )


def _usage_from_result(result: Any, prompt: str = "", model: str = "", image_inputs: int = 0) -> dict[str, int]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    image_count = len(data) if isinstance(data, list) else 0
    prompt_tokens = count_text_tokens(prompt, model) if prompt else 0
    image_input_tokens = max(0, int(image_inputs or 0)) * DEFAULT_IMAGE_INPUT_TOKENS
    image_output_tokens = image_count * DEFAULT_IMAGE_OUTPUT_TOKENS
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": 0,
        "image_count": image_count,
        "image_input_tokens": image_input_tokens,
        "image_output_tokens": image_output_tokens,
        "total_tokens": prompt_tokens + image_input_tokens + image_output_tokens,
        "estimated": True,
    }


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


def _stream_image_count(chunk: str) -> int:
    count = 0
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
        items = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(items, list):
            count += len(items)
    return count


class ChatGPTImageProxy:
    async def handle_generation(self, request: Request, api_key: dict[str, Any], body_bytes: bytes) -> JSONResponse | StreamingResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:16]
        try:
            body = await request.json()
        except Exception as exc:
            return _openai_error(f"invalid JSON body: {exc}", 400, "invalid_request", "invalid_request_error")
        if not isinstance(body, dict):
            return _openai_error("JSON body must be an object", 400, "invalid_request", "invalid_request_error")
        body.setdefault("model", "gpt-image-2")
        proxy_live_service.start(
            request_id=request_id,
            api_key=api_key,
            path="/v1/images/generations",
            method=request.method,
            model=str(body.get("model") or ""),
            request_bytes=len(body_bytes),
            stream=bool(body.get("stream")),
        )
        return await self._run_image_call(
            request_id=request_id,
            api_key=api_key,
            path="/v1/images/generations",
            method=request.method,
            model=str(body.get("model") or ""),
            request_bytes=len(body_bytes),
            started=started,
            stream=bool(body.get("stream")),
            prompt=str(body.get("prompt") or ""),
            image_inputs=0,
            call=lambda: openai_v1_image_generations.handle(body),
        )

    async def handle_edit(self, request: Request, api_key: dict[str, Any], body_bytes: bytes) -> JSONResponse | StreamingResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:16]
        try:
            payload, image_sources = await parse_image_edit_request(request)
            payload["images"] = await read_image_sources(image_sources)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
            message = str(detail.get("error") or detail.get("message") or "invalid image edit request")
            return _openai_error(message, int(exc.status_code), "invalid_request", "invalid_request_error")
        payload.setdefault("model", "gpt-image-2")
        proxy_live_service.start(
            request_id=request_id,
            api_key=api_key,
            path="/v1/images/edits",
            method=request.method,
            model=str(payload.get("model") or ""),
            request_bytes=len(body_bytes),
            stream=bool(payload.get("stream")),
        )
        return await self._run_image_call(
            request_id=request_id,
            api_key=api_key,
            path="/v1/images/edits",
            method=request.method,
            model=str(payload.get("model") or ""),
            request_bytes=len(body_bytes),
            started=started,
            stream=bool(payload.get("stream")),
            prompt=str(payload.get("prompt") or ""),
            image_inputs=len(payload.get("images") or []),
            call=lambda: openai_v1_image_edit.handle(payload),
        )

    async def _run_image_call(
        self,
        *,
        request_id: str,
        api_key: dict[str, Any],
        path: str,
        method: str,
        model: str,
        request_bytes: int,
        started: float,
        stream: bool,
        prompt: str,
        image_inputs: int,
        call,
    ) -> JSONResponse | StreamingResponse:
        tracking_token = account_service.start_attempt_tracking()
        try:
            result = await run_in_threadpool(call)
            if stream:
                attempts = account_service.current_attempts()
                account_service.stop_attempt_tracking(tracking_token)
                proxy_live_service.update(request_id, {"stream": True, "attempts": attempts, "attempt_count": len(attempts)})
                return self._stream_response(request_id, api_key, path, method, model, request_bytes, started, result, attempts, prompt, image_inputs)

            attempts = account_service.stop_attempt_tracking(tracking_token)
            content = json.dumps(result, ensure_ascii=False).encode("utf-8")
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._record(
                request_id,
                api_key,
                path,
                method,
                model,
                200,
                latency_ms,
                True,
                request_bytes,
                len(content),
                attempts,
                stream=False,
                usage=_usage_from_result(result, prompt, model, image_inputs),
            )
            return JSONResponse(content=result)
        except ImageGenerationError as exc:
            attempts = account_service.stop_attempt_tracking(tracking_token)
            latency_ms = int((time.perf_counter() - started) * 1000)
            error_payload = exc.to_openai_error()
            error_message = str((error_payload.get("error") or {}).get("message") or str(exc))
            status_code = int(getattr(exc, "status_code", 502) or 502)
            self._record(
                request_id,
                api_key,
                path,
                method,
                model,
                status_code,
                latency_ms,
                False,
                request_bytes,
                len(json.dumps(error_payload, ensure_ascii=False).encode("utf-8")),
                attempts,
                stream=stream,
                error=_attempt_error(attempts, error_message),
            )
            return JSONResponse(status_code=status_code, content=error_payload)
        except Exception as exc:
            attempts = account_service.stop_attempt_tracking(tracking_token)
            latency_ms = int((time.perf_counter() - started) * 1000)
            error = _attempt_error(attempts, str(exc))
            self._record(
                request_id,
                api_key,
                path,
                method,
                model,
                502,
                latency_ms,
                False,
                request_bytes,
                len(error.encode("utf-8")),
                attempts,
                stream=stream,
                error=error,
            )
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
        prompt: str,
        image_inputs: int,
    ) -> StreamingResponse:
        response_bytes = 0
        chunk_count = 0
        stream_error = ""
        image_count = 0

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
            nonlocal response_bytes, chunk_count, image_count
            proxy_live_service.log(request_id, "stream opened")
            try:
                for chunk in sse_json_stream(tracked_items()):
                    encoded = chunk.encode("utf-8")
                    chunk_count += 1
                    response_bytes += len(encoded)
                    image_count += _stream_image_count(chunk)
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
                    usage=_usage_from_result({"data": [{}] * image_count}, prompt, model, image_inputs),
                    error=stream_error,
                )

        return StreamingResponse(
            iterator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
    ) -> None:
        proxy_usage_service.record({
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
        })


chatgpt_image_proxy = ChatGPTImageProxy()
