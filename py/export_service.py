"""导出服务 - 对接 chatgpt2api 和 infinite-canvas 项目"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .config_service import config_service, ROOT_DIR
from .account_service import account_service

# 东八区时间
TZ_HKT = timezone(timedelta(hours=8))


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """解码 JWT payload"""
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _format_timestamp(value: Any) -> str:
    """Unix 时间戳转东八区 ISO 字符串"""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(TZ_HKT).isoformat(timespec="seconds")


def export_to_chatgpt2api(ids: list[str] | None = None) -> dict[str, Any]:
    """导出为 chatgpt2api 兼容格式（accounts.json + auth_keys.json 格式）

    返回格式: { "accounts": [...], "auth_keys": [...] }
    可直接写入 chatgpt2api 的 data 目录
    """
    accounts = account_service.export_json(ids)
    if not accounts:
        return {"accounts": [], "auth_keys": [], "count": 0}

    export_accounts: list[dict[str, Any]] = []
    export_auth_keys: list[dict[str, Any]] = []

    for account in accounts:
        access_token = str(account.get("access_token") or "").strip()
        refresh_token_val = str(account.get("refresh_token") or "").strip()
        id_token = str(account.get("id_token") or "").strip()

        if not access_token or not refresh_token_val or not id_token:
            continue

        access_claims = _decode_jwt_payload(access_token)
        id_claims = _decode_jwt_payload(id_token)
        access_auth = access_claims.get("https://api.openai.com/auth") or {}
        id_auth = id_claims.get("https://api.openai.com/auth") or {}
        profile = access_claims.get("https://api.openai.com/profile") or {}

        email = (
            str(account.get("email") or "").strip()
            or str(profile.get("email") or "").strip()
            or str(id_claims.get("email") or "").strip()
        )
        account_id = (
            str(account.get("account_id") or "").strip()
            or str(access_auth.get("chatgpt_account_id") or "").strip()
            or str(id_auth.get("chatgpt_account_id") or "").strip()
        )
        expired = (
            str(account.get("expired") or "").strip()
            or _format_timestamp(access_claims.get("exp"))
        )
        last_refresh = (
            str(account.get("last_refresh") or "").strip()
            or _format_timestamp(access_claims.get("iat"))
            or _format_timestamp(access_claims.get("nbf"))
        )

        # accounts 格式（chatgpt2api accounts.json 用 access_token 做 key）
        export_accounts.append({
            "access_token": access_token,
            "refresh_token": refresh_token_val,
            "id_token": id_token,
            "email": email,
            "account_id": account_id,
            "type": "free",
            "status": "正常",
            "quota": int(account.get("quota") or 0),
            "last_used_at": account.get("last_used_at") or "",
            "oauth_client_id": account.get("oauth_client_id") or "",
            "oauth_scope": account.get("oauth_scope") or "",
        })

        # auth_keys 格式（chatgpt2api 兼容格式）
        export_auth_keys.append({
            "type": "codex",
            "email": email,
            "expired": expired,
            "id_token": id_token,
            "account_id": account_id,
            "access_token": access_token,
            "last_refresh": last_refresh,
            "refresh_token": refresh_token_val,
        })

    # 如果需要写入文件到 chatgpt2api 目录
    try:
        config = config_service.get()
        chat_config = config.get("chatgpt2api") or {}
        export_dir = Path(chat_config.get("export_dir") or "../chatgpt2api/data")
        if not export_dir.is_absolute():
            export_dir = (ROOT_DIR / export_dir).resolve()
        export_dir.mkdir(parents=True, exist_ok=True)

        # 写入 accounts.json
        accounts_path = export_dir / "accounts.json"
        accounts_path.write_text(
            json.dumps(export_accounts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # 写入 auth_keys.json
        auth_keys_path = export_dir / "auth_keys.json"
        auth_keys_path.write_text(
            json.dumps(export_auth_keys, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass  # 文件写入仅 best-effort

    return {"accounts": export_accounts, "auth_keys": export_auth_keys, "count": len(export_accounts)}


def export_to_infinite_canvas(ids: list[str] | None = None) -> dict[str, Any]:
    """导出为 infinite-canvas 兼容的 Model Channel 配置

    通过 infinite-canvas 的 POST /api/admin/settings API 推送渠道配置
    """
    accounts = account_service.export_json(ids)
    if not accounts:
        return {"channels": [], "count": 0, "pushed": False}

    # 构建 ModelChannel 数组
    channels: list[dict[str, Any]] = []
    for account in accounts:
        access_token = str(account.get("access_token") or "").strip()
        email = str(account.get("email") or "").strip()
        if not access_token:
            continue

        # 解码 access_token 获取可用的模型信息
        claims = _decode_jwt_payload(access_token)
        profile = claims.get("https://api.openai.com/profile") or {}
        email = email or profile.get("email") or "unknown"

        channels.append({
            "protocol": "openai",
            "name": f"GPT-{email.split('@')[0][:20]}",
            "baseUrl": "https://api.openai.com",
            "apiKey": access_token,
            "models": ["gpt-4o", "dall-e-3", "gpt-image-2"],
            "weight": 1,
            "enabled": True,
            "remark": f"auto-exported from gpt-web-cf-make, account: {email}",
        })

    if not channels:
        return {"channels": [], "count": 0, "pushed": False}

    # 尝试推送到 infinite-canvas API
    pushed = False
    try:
        config = config_service.get()
        ic_config = config.get("infinite_canvas") or {}
        api_url = str(ic_config.get("api_url") or "").rstrip("/")
        admin_username = str(ic_config.get("admin_username") or "admin")
        admin_password = str(ic_config.get("admin_password") or "admin")

        if api_url:
            import urllib.request
            import urllib.error

            # 获取 JWT token
            login_data = json.dumps({"username": admin_username, "password": admin_password}).encode()
            login_req = urllib.request.Request(
                f"{api_url}/api/auth/login",
                data=login_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(login_req, timeout=10) as resp:
                    login_body = json.loads(resp.read().decode())
                    jwt_token = login_body.get("token") or login_body.get("data", {}).get("token") or ""
            except Exception:
                jwt_token = ""

            if jwt_token:
                # 推送设置
                settings_payload = json.dumps({
                    "private": json.dumps({"channels": channels}),
                }).encode()
                settings_req = urllib.request.Request(
                    f"{api_url}/api/admin/settings",
                    data=settings_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {jwt_token}",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(settings_req, timeout=10) as resp:
                        if 200 <= resp.status < 300:
                            pushed = True
                except Exception:
                    pass
    except Exception:
        pass

    return {"channels": channels, "count": len(channels), "pushed": pushed}
