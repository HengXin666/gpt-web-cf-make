"""OpenAI 兼容反代访问密钥管理。"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from .config_service import DATA_DIR
from .config_service import config_service
from ..shared.models import _now

KEYS_FILE = DATA_DIR / "proxy_keys.json"


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ProxyAuthService:
    """保存和校验用户请求反代时使用的 API Key。"""

    def __init__(self, store_file: Path = KEYS_FILE):
        self._store_file = store_file
        self._lock = RLock()
        self._keys: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            if self._store_file.exists():
                data = json.loads(self._store_file.read_text(encoding="utf-8"))
                self._keys = [self._normalize(item) for item in data if isinstance(item, dict)]
                self._keys = [item for item in self._keys if item]
        except Exception:
            self._keys = []

    def _save(self) -> None:
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        self._store_file.write_text(
            json.dumps(self._keys, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        key_hash = str(item.get("key_hash") or "").strip()
        if not key_hash:
            return {}
        return {
            "id": str(item.get("id") or uuid.uuid4().hex[:12]),
            "name": str(item.get("name") or "默认密钥").strip() or "默认密钥",
            "key_hash": key_hash,
            "key": str(item.get("key") or "").strip(),
            "enabled": bool(item.get("enabled", True)),
            "created_at": str(item.get("created_at") or _now()),
            "last_used_at": str(item.get("last_used_at") or ""),
        }

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        result = {
            "id": item["id"],
            "name": item["name"],
            "enabled": item["enabled"],
            "created_at": item["created_at"],
            "last_used_at": item.get("last_used_at") or "",
        }
        if bool(config_service.get_reverse_proxy_config().get("remember_keys")) and item.get("key"):
            result["key"] = item.get("key")
        return result

    def list_keys(self) -> list[dict[str, Any]]:
        with self._lock:
            self._load()
            return [self._public(item) for item in self._keys]

    def create_key(self, name: str = "") -> dict[str, Any]:
        with self._lock:
            self._load()
            raw_key = f"sk-gwm-{secrets.token_urlsafe(32)}"
            item = {
                "id": uuid.uuid4().hex[:12],
                "name": str(name or "默认密钥").strip() or "默认密钥",
                "key_hash": _hash_key(raw_key),
                "key": raw_key if bool(config_service.get_reverse_proxy_config().get("remember_keys")) else "",
                "enabled": True,
                "created_at": _now(),
                "last_used_at": "",
            }
            self._keys.append(item)
            self._save()
            return {**self._public(item), "key": raw_key}

    def update_key(self, key_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            self._load()
            for index, item in enumerate(self._keys):
                if item.get("id") != key_id:
                    continue
                next_item = deepcopy(item)
                if "name" in updates:
                    next_item["name"] = str(updates.get("name") or "").strip() or next_item["name"]
                if "enabled" in updates:
                    next_item["enabled"] = bool(updates["enabled"])
                self._keys[index] = next_item
                self._save()
                return self._public(next_item)
        return None

    def delete_key(self, key_id: str) -> bool:
        with self._lock:
            self._load()
            before = len(self._keys)
            self._keys = [item for item in self._keys if item.get("id") != key_id]
            if len(self._keys) == before:
                return False
            self._save()
            return True

    def forget_plain_keys(self) -> None:
        with self._lock:
            self._load()
            changed = False
            for item in self._keys:
                if item.get("key"):
                    item["key"] = ""
                    changed = True
            if changed:
                self._save()

    def validate(self, raw_key: str) -> dict[str, Any] | None:
        candidate = str(raw_key or "").strip()
        if not candidate:
            return None
        candidate_hash = _hash_key(candidate)
        with self._lock:
            self._load()
            for index, item in enumerate(self._keys):
                stored_hash = str(item.get("key_hash") or "")
                if not bool(item.get("enabled", True)):
                    continue
                if not hmac.compare_digest(stored_hash, candidate_hash):
                    continue
                self._keys[index]["last_used_at"] = _now()
                self._save()
                return self._public(self._keys[index])
        return None


proxy_auth_service = ProxyAuthService()
