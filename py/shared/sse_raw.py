"""Monkey-patch uvicorn to support raw SSE streaming without HTTP chunked encoding.

Adds ``Transfer-Encoding: identity`` response header support.
When this header is present, uvicorn sends the body as raw bytes
(no chunked encoding) and closes the connection after the response.

Import this module early (before uvicorn starts) to install the patch.
"""

from __future__ import annotations

from typing import Any

_INSTALLED = False


def _patch_httptools() -> None:
    import uvicorn.protocols.http.httptools_impl as impl

    _original_send = impl.RequestResponseCycle.send

    async def _patched_send(self: Any, message: dict[str, Any]) -> None:
        # ── Intercept response start ────────────────────────────────
        if not self.response_started and message["type"] == "http.response.start":
            headers: list[tuple[bytes, bytes]] = message.get("headers", [])
            for name, value in headers:
                if name.lower() == b"transfer-encoding" and value.lower() == b"identity":
                    # Replace Transfer-Encoding: identity with a huge
                    # Content-Length so uvicorn writes raw bytes.
                    new_headers = [
                        (n, v) for n, v in headers
                        if n.lower() != b"transfer-encoding"
                    ]
                    new_headers.append((b"connection", b"close"))
                    # 2^63-1 is effectively infinite for a streaming response
                    new_headers.append((b"content-length", b"9223372036854775807"))
                    message = {**message, "headers": new_headers}
                    self.__sse_raw_mode = True  # type: ignore[attr-defined]
                    break

        # ── Before last body message, fix expected_content_length ───
        if (
            message["type"] == "http.response.body"
            and getattr(self, "__sse_raw_mode", False)
            and not message.get("more_body", True)
        ):
            self.expected_content_length = 0

        await _original_send(self, message)

    impl.RequestResponseCycle.send = _patched_send  # type: ignore[attr-defined]


def _patch_h11() -> None:
    import uvicorn.protocols.http.h11_impl as impl

    _original_send = impl.RequestResponseCycle.send

    async def _patched_send(self: Any, message: dict[str, Any]) -> None:
        if not self.response_started and message["type"] == "http.response.start":
            headers: list[tuple[bytes, bytes]] = message.get("headers", [])
            for name, value in headers:
                if name.lower() == b"transfer-encoding" and value.lower() == b"identity":
                    new_headers = [
                        (n, v) for n, v in headers
                        if n.lower() != b"transfer-encoding"
                    ]
                    new_headers.append((b"connection", b"close"))
                    new_headers.append((b"content-length", b"9223372036854775807"))
                    message = {**message, "headers": new_headers}
                    self.__sse_raw_mode = True  # type: ignore[attr-defined]
                    break

        if (
            message["type"] == "http.response.body"
            and getattr(self, "__sse_raw_mode", False)
            and not message.get("more_body", True)
        ):
            self.expected_content_length = 0

        await _original_send(self, message)

    impl.RequestResponseCycle.send = _patched_send  # type: ignore[attr-defined]


def install() -> None:
    """Install the monkey-patch. Safe to call multiple times."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    try:
        _patch_httptools()
    except ImportError:
        pass

    try:
        _patch_h11()
    except ImportError:
        pass
