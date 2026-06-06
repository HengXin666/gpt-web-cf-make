"""代理池数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from ..shared.models import _new_id, _now


@dataclass
class ProxyNode:
    """代理节点模型 - 对应 proxy_pool.json 中的节点记录"""
    id: str = field(default_factory=_new_id)
    name: str = ""                        # 显示名，如 "HK-01"
    protocol: str = ""                    # http | https | socks5 | ss | vmess | trojan | vless | hysteria2 | ...
    server: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # 协议特有字段
    proxy_url: str = ""                   # curl_cffi 可用的代理 URL（空 = 需要本地中转）
    subscription_id: str = ""             # 来源订阅 ID（手动添加为空）
    pool: str = "api"                     # api | register — 节点归类
    # 测试结果
    latency_ms: int = -1                  # -1 = 未测试
    score: int = -1                       # 纯净度评分，-1 = 未测试
    grade: str = ""                       # pure/clean/moderate/risky/dirty
    country: str = ""
    city: str = ""
    isp: str = ""
    ip_type: str = ""                     # residential/datacenter/mobile
    last_tested_at: str = ""
    last_error: str = ""
    enabled: bool = True
    # 注册流水线失败统计
    register_otp_timeouts: int = 0        # 邮箱验证码超时次数
    register_token_failures: int = 0      # token/凭证获取失败次数
    register_success: int = 0             # 注册成功次数
    register_total: int = 0               # 总尝试次数
    register_last_error: str = ""         # 最近一次错误
    register_last_used_at: str = ""       # 最近一次用于注册的时间
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProxyNode:
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
