"""账号刷新任务 - 为前端提供逐账号 SSE 日志。"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any

from .account_service import account_service
from .token_refresh_service import token_refresh_service


class RefreshJobService:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create(self, action: str, ids: list[str]) -> dict[str, Any]:
        action = "token" if action == "token" else "quota"
        job_id = uuid.uuid4().hex
        event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "action": action,
                "ids": ids,
                "queue": event_queue,
                "done": False,
                "created_at": time.time(),
            }
        thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
        thread.start()
        return {"job_id": job_id, "action": action, "total": len(ids)}

    def _push(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job:
            job["queue"].put(event)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return

        action = str(job["action"])
        ids = list(job["ids"])
        ok_count = 0
        fail_count = 0
        failed_ids: list[str] = []

        self._push(job_id, {"type": "start", "action": action, "total": len(ids)})
        for index, account_id in enumerate(ids, start=1):
            account = account_service.get_account(account_id) or {}
            email = str(account.get("email") or account_id)
            self._push(job_id, {"type": "progress", "status": "running", "index": index, "total": len(ids), "id": account_id, "email": email})
            try:
                result = (
                    token_refresh_service.refresh_single(account_id)
                    if action == "token"
                    else account_service.refresh_account_quota(account_id)
                )
                if result.get("ok"):
                    updated = account_service.get_account(account_id) or {}
                    ok_count += 1
                    self._push(job_id, {
                        "type": "progress",
                        "status": "success",
                        "index": index,
                        "total": len(ids),
                        "id": account_id,
                        "email": str(updated.get("email") or email),
                        "quota": updated.get("quota"),
                        "plan_type": updated.get("plan_type"),
                    })
                else:
                    fail_count += 1
                    failed_ids.append(account_id)
                    self._push(job_id, {
                        "type": "progress",
                        "status": "failed",
                        "index": index,
                        "total": len(ids),
                        "id": account_id,
                        "email": email,
                        "error": str(result.get("error") or "unknown"),
                    })
            except Exception as exc:
                fail_count += 1
                failed_ids.append(account_id)
                self._push(job_id, {
                    "type": "progress",
                    "status": "failed",
                    "index": index,
                    "total": len(ids),
                    "id": account_id,
                    "email": email,
                    "error": str(exc),
                })

        done = {"type": "done", "action": action, "refreshed": ok_count, "failed": fail_count, "failed_ids": failed_ids}
        self._push(job_id, done)
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["done"] = True

    def events(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            yield "event: error\ndata: {\"error\":\"job not found\"}\n\n"
            return

        event_queue: queue.Queue[dict[str, Any]] = job["queue"]
        while True:
            try:
                event = event_queue.get(timeout=15)
            except queue.Empty:
                yield ": ping\n\n"
                continue

            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            if event.get("type") == "done":
                return


refresh_job_service = RefreshJobService()
