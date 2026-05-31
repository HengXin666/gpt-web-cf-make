"""chatgpt2api 适配代理配置。"""

from __future__ import annotations

from ..services.config_service import config_service


class ProxySettingsStore:
    def build_session_kwargs(self, **session_kwargs):
        proxy = config_service.get_proxy()
        if proxy:
            session_kwargs["proxy"] = proxy
        return session_kwargs


proxy_settings = ProxySettingsStore()
