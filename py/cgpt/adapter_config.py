"""chatgpt2api 适配配置。"""

from __future__ import annotations

from ..config_service import config_service


class AdapterConfig:
    @property
    def timeout_seconds(self) -> int:
        value = config_service.get_reverse_proxy_config().get("timeout_seconds") or 120
        return max(5, int(value))

    @property
    def image_poll_timeout_secs(self) -> int:
        value = (config_service.get_reverse_proxy_config().get("image_poll_timeout_secs") or self.timeout_seconds)
        return max(1, int(value))

    @property
    def image_poll_interval_secs(self) -> float:
        value = (config_service.get_reverse_proxy_config().get("image_poll_interval_secs") or 10.0)
        return max(0.5, float(value))

    @property
    def image_poll_initial_wait_secs(self) -> float:
        value = (config_service.get_reverse_proxy_config().get("image_poll_initial_wait_secs") or 10.0)
        return max(0.0, float(value))

    @property
    def continue_on_timeout(self) -> bool:
        return bool(config_service.get_reverse_proxy_config().get("continue_on_timeout"))

    @property
    def global_system_prompt(self) -> str:
        value = config_service.get_reverse_proxy_config().get("global_system_prompt") or ""
        return str(value).strip()


config = AdapterConfig()
