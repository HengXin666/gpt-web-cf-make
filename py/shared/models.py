"""数据模型定义 - 使用dataclass保证类型安全"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    """UTC 时间戳"""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """生成唯一 ID"""
    return uuid.uuid4().hex[:12]


@dataclass
class Account:
    """账号模型 - 对应 accounts.json 中的每条记录"""
    id: str = field(default_factory=_new_id)
    email: str = ""
    password: str = ""
    access_token: str = ""
    refresh_token: str = ""
    id_token: str = ""
    session_token: str = ""
    oauth_client_id: str = ""
    oauth_profile: str = "platform"
    oauth_scope: str = ""
    plan_type: str = "free"
    status: str = "normal"  # normal | abnormal | limited | disabled
    quota: int = 0
    quota_reset_at: str = ""
    created_at: str = field(default_factory=_now)
    last_refreshed_at: str = ""
    last_used_at: str = ""
    refresh_error: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    proxy_node_id: str = ""               # 固定代理节点分配

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # 状态中英文映射
    _STATUS_MAP = {"正常": "normal", "异常": "abnormal", "限流": "limited", "禁用": "disabled"}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Account:
        """从字典创建 Account，过滤无关字段，标准化状态值"""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        if "tags" in filtered and not isinstance(filtered["tags"], list):
            filtered["tags"] = []
        if "status" in filtered and filtered["status"] in cls._STATUS_MAP:
            filtered["status"] = cls._STATUS_MAP[filtered["status"]]
        return cls(**filtered)


@dataclass
class RegisterConfig:
    """注册机配置"""
    mail: dict[str, Any] = field(default_factory=lambda: {
        "request_timeout": 30,
        "wait_timeout": 30,
        "wait_interval": 2,
        "proxy": "",
        "providers": [],
    })
    proxy: str = ""
    total: int = 1
    threads: int = 1
    mode: str = "total"  # total | quota | available
    target_quota: int = 100
    target_available: int = 10
    check_interval: int = 5
    fixed_password: str = ""
    proxy_node_id: str = ""               # 注册机固定代理节点
    enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegisterConfig:
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class RegisterStats:
    """注册机统计信息"""
    job_id: str = ""
    success: int = 0
    fail: int = 0
    done: int = 0
    running: int = 0
    threads: int = 1
    elapsed_seconds: float = 0.0
    avg_seconds: float = 0.0
    success_rate: float = 0.0
    current_quota: int = 0
    current_available: int = 0
    started_at: str = ""
    updated_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LogEntry:
    """日志条目"""
    time: str = ""
    text: str = ""
    level: str = "info"  # info | yellow | green | red

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
