"""反代请求实时状态和 SSE 订阅。"""

from __future__ import annotations

import json
import queue
from copy import deepcopy
from threading import RLock
from typing import Any

from ..shared.models import _now


class ProxyLiveService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._active: dict[str, dict[str, Any]] = {}
        self._logs: list[dict[str, Any]] = []
        self._subscribers: set[queue.Queue[str]] = set()

    def active(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(item) for item in self._active.values()]

    def start(
        self,
        *,
        request_id: str,
        api_key: dict[str, Any],
        path: str,
        method: str,
        model: str,
        request_bytes: int,
        stream: bool = False,
        request_text: str = "",
        request_image_hashes: list[str] | None = None,
    ) -> None:
        item = {
            "request_id": request_id,
            "time": _now(),
            "api_key": {"id": api_key.get("id"), "name": api_key.get("name")},
            "account": {"id": None, "email": None},
            "path": path,
            "method": method,
            "model": model,
            "status_code": 102,
            "latency_ms": 0,
            "success": False,
            "state": "running",
            "stream": stream,
            "request_bytes": request_bytes,
            "response_bytes": 0,
            "stream_chunks": 0,
            "stream_logs": [],
            "usage": {},
            "error": "",
            "attempts": [],
            "attempt_count": 0,
            "request_text": request_text[:3000] if request_text else "",
            "request_image_hashes": request_image_hashes or [],
        }
        with self._lock:
            self._active[request_id] = item
        self.publish({"type": "started", "record": item})
        self.log(request_id, "request started", record=item)

    def update(self, request_id: str, updates: dict[str, Any], stream_log: str = "") -> None:
        with self._lock:
            item = self._active.get(request_id)
            if not item:
                return
            item.update(deepcopy(updates))
            if stream_log:
                logs = list(item.get("stream_logs") or [])
                logs.append({"time": _now(), "message": stream_log})
                item["stream_logs"] = logs[-120:]
            payload = deepcopy(item)
        self.publish({"type": "updated", "record": payload})

    def complete(self, record: dict[str, Any]) -> None:
        item = deepcopy(record)
        item["state"] = "success" if item.get("success") else "failed"
        request_id = str(item.get("request_id") or "")
        with self._lock:
            active_item = deepcopy(self._active.get(request_id) or {}) if request_id else {}
            if request_id:
                self._active.pop(request_id, None)
        for key in ("stream", "stream_chunks", "stream_logs"):
            if key in active_item and (key not in item or not item.get(key)):
                item[key] = active_item[key]
        self.publish({"type": "completed", "record": item})
        status = item.get("status_code") or "ERR"
        level = "info" if item.get("success") else "error"
        self.log(request_id, f"request completed: HTTP {status}", level=level, record=item)

    def log(self, request_id: str, message: str, level: str = "info", record: dict[str, Any] | None = None) -> None:
        item = {
            "time": _now(),
            "request_id": request_id,
            "level": level,
            "message": message,
            "record": deepcopy(record) if record else None,
        }
        with self._lock:
            self._logs = [item, *self._logs][:200]
        self.publish({"type": "log", "log": item})

    def publish(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except Exception:
                pass

    def subscribe(self) -> queue.Queue[str]:
        subscriber: queue.Queue[str] = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(subscriber)
            active = [deepcopy(item) for item in self._active.values()]
            logs = [deepcopy(item) for item in self._logs[:80]]
        subscriber.put_nowait(json.dumps({"type": "snapshot", "active": active, "logs": logs}, ensure_ascii=False))
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[str]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)


proxy_live_service = ProxyLiveService()
