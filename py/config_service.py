"""配置服务 - 读写 config.json，提供全局配置访问"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

# 项目根目录 (gpt-web-cf-make/)
ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"

# 默认配置
_DEFAULT_CONFIG: dict[str, Any] = {
    "proxy": "",
    "oauth_profile": "platform",
    "oauth": {
        "client_id": "app_2SKx67EdpoN0G6j64rFvigXD",
        "redirect_uri": "https://platform.openai.com/auth/callback",
        "auth_base": "https://auth.openai.com",
        "audience": "https://api.openai.com/v1",
        "scope": "openid profile email offline_access",
        "auth0_client": "eyJuYW1lIjoiYXV0aDAtc3BhLWpzIiwidmVyc2lvbiI6IjEuMjEuMCJ9",
    },
    "codex_oauth": {
        "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "redirect_uri": "http://localhost:1455/auth/callback",
        "scope": "openid email profile offline_access",
    },
    "token_refresh": {
        "enabled": True,
        "interval_minutes": 60,
        "expiring_days": 5,
        "max_workers": 10,
        "retry_failed_only": True,
    },
    "http": {
        "version": "http2",
    },
    "reverse_proxy": {
        "enabled": True,
        "upstream_base_url": "https://api.openai.com",
        "strategy": "round_robin",
        "timeout_seconds": 120,
        "max_retries": 2,
        "continue_on_timeout": False,
        "remember_keys": False,
        "models": [
            "gpt-5.5",
            "gpt-5.1",
            "gpt-5",
            "gpt-4.1",
            "gpt-image-2",
            "sora-2",
        ],
    },
}


class ConfigService:
    """全局配置服务 - 读写 config.json，线程安全"""

    def __init__(self, config_file: Path = CONFIG_FILE):
        self._config_file = config_file
        self._lock = RLock()
        self._config = self._load()

    def _load(self) -> dict[str, Any]:
        """加载配置，合并默认值"""
        config = deepcopy(_DEFAULT_CONFIG)
        try:
            if self._config_file.exists():
                data = json.loads(self._config_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._deep_merge(config, data)
        except Exception:
            pass
        return config

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """深度合并配置"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigService._deep_merge(base[key], value)
            else:
                base[key] = value

    def _save(self) -> None:
        """保存配置到文件"""
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        self._config_file.write_text(
            json.dumps(self._config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self) -> dict[str, Any]:
        """获取完整配置（深拷贝）"""
        with self._lock:
            return deepcopy(self._config)

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        """更新配置并保存"""
        with self._lock:
            self._deep_merge(self._config, updates)
            self._save()
            return deepcopy(self._config)

    def get_proxy(self) -> str:
        """获取代理 URL"""
        return str(self._config.get("proxy") or "").strip()

    def get_oauth(self, profile: str = "platform") -> dict[str, Any]:
        """获取 OAuth 配置"""
        key = "codex_oauth" if str(profile).strip().lower() == "codex" else "oauth"
        return dict(self._config.get(key) or {})

    def get_token_refresh_config(self) -> dict[str, Any]:
        """获取 Token 刷新配置"""
        return dict(self._config.get("token_refresh") or {})

    def get_http_version(self) -> str:
        """获取 curl_cffi HTTP 版本策略: http2 或 http1.1"""
        http_config = self._config.get("http") or {}
        value = str(http_config.get("version") or "http2").strip().lower()
        return "http1.1" if value in {"http1", "http1.1", "1.1", "force_http1"} else "http2"

    def get_reverse_proxy_config(self) -> dict[str, Any]:
        """获取 OpenAI 兼容反代配置。"""
        return dict(self._config.get("reverse_proxy") or {})


# 全局单例
config_service = ConfigService()
