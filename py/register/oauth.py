"""OAuth 辅助函数 - PKCE、URL 构建、code 交换、refresh_token 续期"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..shared.http_client import request_local_retry

# 默认 OAuth 配置
AUTH_BASE = "https://auth.openai.com"
PLATFORM_BASE = "https://platform.openai.com"
PLATFORM_OAUTH_CLIENT_ID = "app_2SKx67EdpoN0G6j64rFvigXD"
PLATFORM_OAUTH_REDIRECT_URI = f"{PLATFORM_BASE}/auth/callback"
PLATFORM_AUTH0_CLIENT = "eyJuYW1lIjoiYXV0aDAtc3BhLWpzIiwidmVyc2lvbiI6IjEuMjEuMCJ9"


def generate_pkce() -> tuple[str, str]:
    """生成 PKCE code_verifier 和 code_challenge (S256)"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def build_platform_auth_url(oauth: dict[str, Any], code_challenge: str, login_hint: str = "", device_id: str = "") -> str:
    """构建 Platform OAuth 授权 URL"""
    params = {
        "issuer": oauth.get("auth_base", AUTH_BASE),
        "client_id": oauth.get("client_id", PLATFORM_OAUTH_CLIENT_ID),
        "audience": oauth.get("audience", "https://api.openai.com/v1"),
        "redirect_uri": oauth.get("redirect_uri", PLATFORM_OAUTH_REDIRECT_URI),
        "device_id": device_id or secrets.token_hex(16),
        "screen_hint": "login_or_signup",
        "max_age": "0",
        "scope": oauth.get("scope", "openid profile email offline_access"),
        "response_type": "code",
        "response_mode": "query",
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "auth0Client": oauth.get("auth0_client", PLATFORM_AUTH0_CLIENT),
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{oauth.get('auth_base', AUTH_BASE).rstrip('/')}/api/accounts/authorize?{urllib.parse.urlencode(params)}"


def build_codex_auth_url(oauth: dict[str, Any], code_challenge: str, login_hint: str = "") -> str:
    """构建 Codex/CLIProxy OAuth 授权 URL"""
    params = {
        "client_id": oauth["client_id"],
        "response_type": "code",
        "redirect_uri": oauth["redirect_uri"],
        "scope": oauth["scope"],
        "state": secrets.token_urlsafe(32),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_BASE}/oauth/authorize?{urllib.parse.urlencode(params)}"


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """解码 JWT payload（不解密签名）"""
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload).decode())
    except Exception:
        return {}


def _open_form_request(opener: urllib.request.OpenerDirector, request: urllib.request.Request, timeout: int) -> tuple[str, int, bool]:
    def call(index: int) -> tuple[str, int, bool]:
        with opener.open(request, timeout=timeout + (10 if index else 0)) as response:
            text = response.read().decode("utf-8", errors="replace")
            status_code = response.status
            return text, status_code, 200 <= status_code < 300

    return request_local_retry(call)


def exchange_code(
    oauth: dict[str, Any],
    code: str,
    code_verifier: str,
    proxy: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    """用 authorization_code 交换 access_token + refresh_token"""
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": oauth["redirect_uri"],
        "client_id": oauth["client_id"],
        "code_verifier": code_verifier,
    }).encode()
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        f"{AUTH_BASE}/oauth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "gpt-web-cf-make/0.1"},
        method="POST",
    )
    try:
        text, status_code, ok = _open_form_request(opener, request, timeout)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        status_code = exc.code
        ok = False
    try:
        body: Any = json.loads(text)
    except Exception:
        body = {"raw": text[:1000]}
    return {"status_code": status_code, "ok": ok, "body": body}


def refresh_token(
    oauth: dict[str, Any],
    refresh_token_value: str,
    client_id: str = "",
    scope: str = "",
    proxy: str = "",
    timeout: int = 30,
) -> dict[str, Any]:
    """使用 refresh_token 续期 access_token"""
    client_id = str(client_id or "").strip() or oauth.get("client_id", PLATFORM_OAUTH_CLIENT_ID)
    scope = str(scope or "").strip() or "openid profile email"
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
        "client_id": client_id,
        "scope": scope,
    }).encode()
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        f"{AUTH_BASE}/oauth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "gpt-web-cf-make/0.1",
        },
        method="POST",
    )
    try:
        text, status_code, ok = _open_form_request(opener, request, timeout)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        status_code = exc.code
        ok = False
    try:
        body: Any = json.loads(text)
    except Exception:
        body = {"raw": text[:1000]}
    return {"status_code": status_code, "ok": ok, "body": body}
