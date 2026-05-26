"""OpenAI 兼容反代用量记录。"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .config_service import DATA_DIR
from .proxy_live_service import proxy_live_service
from .proxy_pricing_service import compute_usage_cost
from .shared.models import _now

USAGE_FILE = DATA_DIR / "proxy_usage.jsonl"
USAGE_DB = DATA_DIR / "proxy_usage.sqlite3"


class ProxyUsageService:
    """JSONL 用量日志，便于追加写入和前端查询。"""

    def __init__(self, store_file: Path = USAGE_FILE, db_file: Path = USAGE_DB):
        self._store_file = store_file
        self._db_file = db_file
        self._lock = RLock()

    def _connect(self) -> sqlite3.Connection:
        self._db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proxy_usage (
                request_id TEXT PRIMARY KEY,
                time TEXT NOT NULL,
                api_key_name TEXT,
                model TEXT,
                path TEXT,
                success INTEGER,
                input_tokens INTEGER,
                cached_input_tokens INTEGER,
                output_tokens INTEGER,
                image_input_tokens INTEGER,
                image_output_tokens INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                estimated INTEGER,
                payload_json TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proxy_usage_time ON proxy_usage(time)")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(proxy_usage)").fetchall()}
        if "payload_json" not in columns:
            conn.execute("ALTER TABLE proxy_usage ADD COLUMN payload_json TEXT")
        return conn

    @staticmethod
    def _parse_time(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _record_sqlite(self, payload: dict[str, Any]) -> None:
        cost = payload.get("cost") if isinstance(payload.get("cost"), dict) else {}
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        input_tokens = int(cost.get("input_tokens") or usage.get("prompt_tokens") or 0)
        cached_input_tokens = int(cost.get("cached_input_tokens") or 0)
        output_tokens = int(cost.get("output_tokens") or usage.get("completion_tokens") or 0)
        image_input_tokens = int(cost.get("image_input_tokens") or 0)
        image_output_tokens = int(cost.get("image_output_tokens") or 0)
        total_tokens = input_tokens + output_tokens + image_input_tokens + image_output_tokens
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO proxy_usage (
                    request_id, time, api_key_name, model, path, success,
                    input_tokens, cached_input_tokens, output_tokens, image_input_tokens,
                    image_output_tokens, total_tokens, cost_usd, estimated, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("request_id") or ""),
                    str(payload.get("time") or _now()),
                    str((payload.get("api_key") or {}).get("name") or ""),
                    str(payload.get("model") or ""),
                    str(payload.get("path") or ""),
                    1 if payload.get("success") else 0,
                    input_tokens,
                    cached_input_tokens,
                    output_tokens,
                    image_input_tokens,
                    image_output_tokens,
                    total_tokens,
                    float(cost.get("total_cost_usd") or 0),
                    1 if cost.get("estimated") else 0,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def record(self, entry: dict[str, Any]) -> None:
        payload = {"time": _now(), **entry}
        active = next((item for item in proxy_live_service.active() if item.get("request_id") == payload.get("request_id")), {})
        for key in ("stream", "stream_chunks", "stream_logs"):
            if key in active and (key not in payload or not payload.get(key)):
                payload[key] = active[key]
        payload["cost"] = compute_usage_cost(payload)
        with self._lock:
            self._store_file.parent.mkdir(parents=True, exist_ok=True)
            with self._store_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._record_sqlite(payload)
        proxy_live_service.complete(payload)

    def list_records(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(1000, int(limit or 100)))
        records: list[dict[str, Any]] = []
        with self._lock:
            if self._db_file.exists():
                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT payload_json FROM proxy_usage
                        ORDER BY time DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
                for row in rows:
                    try:
                        item = json.loads(row[0] or "{}")
                    except Exception:
                        continue
                    if isinstance(item, dict):
                        records.append(item)
                if records:
                    return records
            if not self._store_file.exists():
                return []
            lines = self._store_file.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-limit * 2:]):
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                records.append(item)
            if len(records) >= limit:
                break
        return records

    def summary(self, limit: int = 5000) -> dict[str, Any]:
        records = self.list_records(limit)
        total = len(records)
        success = sum(1 for item in records if bool(item.get("success")))
        failed = total - success
        prompt_tokens = sum(int((item.get("usage") or {}).get("prompt_tokens") or 0) for item in records)
        completion_tokens = sum(int((item.get("usage") or {}).get("completion_tokens") or 0) for item in records)
        total_tokens = sum(int((item.get("usage") or {}).get("total_tokens") or 0) for item in records)
        total_cost_usd = round(sum(float((item.get("cost") or {}).get("total_cost_usd") or 0) for item in records), 8)
        by_key: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "success": 0, "failed": 0, "tokens": 0})
        by_model: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "success": 0, "failed": 0, "tokens": 0})
        for item in records:
            usage = item.get("usage") or {}
            tokens = int(usage.get("total_tokens") or 0)
            key_name = str((item.get("api_key") or {}).get("name") or "未知密钥")
            model = str(item.get("model") or "-")
            for bucket in (by_key[key_name], by_model[model]):
                bucket["requests"] += 1
                bucket["tokens"] += tokens
                if item.get("success"):
                    bucket["success"] += 1
                else:
                    bucket["failed"] += 1
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "running": len(proxy_live_service.active()),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "by_key": [{"name": name, **data} for name, data in by_key.items()],
            "by_model": [{"model": model, **data} for model, data in by_model.items()],
            "active": proxy_live_service.active(),
            "recent": records[:100],
        }

    def series(self, minutes: int = 240, bucket_seconds: int = 60) -> dict[str, Any]:
        minutes = max(5, min(24 * 60, int(minutes or 240)))
        bucket_seconds = max(30, min(3600, int(bucket_seconds or 60)))
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
        buckets: dict[int, dict[str, Any]] = {}
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT time, input_tokens, cached_input_tokens, output_tokens,
                           image_input_tokens, image_output_tokens,
                           cost_usd, estimated
                    FROM proxy_usage
                    WHERE time >= ?
                    ORDER BY time ASC
                    """,
                    (start.isoformat(),),
                ).fetchall()
        for row in rows:
            item_time = self._parse_time(row[0])
            bucket = int(item_time.timestamp() // bucket_seconds * bucket_seconds)
            target = buckets.setdefault(bucket, {
                "time": datetime.fromtimestamp(bucket, timezone.utc).isoformat(),
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "image_input_tokens": 0,
                "image_output_tokens": 0,
                "cost_usd": 0.0,
                "estimated": False,
            })
            target["input_tokens"] += int(row[1] or 0)
            target["cached_input_tokens"] += int(row[2] or 0)
            target["output_tokens"] += int(row[3] or 0)
            target["image_input_tokens"] += int(row[4] or 0)
            target["image_output_tokens"] += int(row[5] or 0)
            target["total_tokens"] = target["input_tokens"] + target["output_tokens"] + target["image_input_tokens"] + target["image_output_tokens"]
            target["cost_usd"] = round(float(target["cost_usd"]) + float(row[6] or 0), 8)
            target["estimated"] = bool(target["estimated"] or row[7])
        return {
            "window_minutes": minutes,
            "bucket_seconds": bucket_seconds,
            "points": [buckets[key] for key in sorted(buckets)],
            "total_cost_usd": round(sum(float(item["cost_usd"]) for item in buckets.values()), 8),
        }


proxy_usage_service = ProxyUsageService()
