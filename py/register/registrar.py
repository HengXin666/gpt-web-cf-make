"""PlatformRegistrar - OpenAI 账号自动注册器 (7步注册流程)"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import secrets
import string
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import urllib3
from curl_cffi import requests as curl_requests
from ..shared.http_client import LOCAL_RETRY_ATTEMPTS, get_curl_http_version, install_local_retry, is_local_retryable_error

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 常量 ─────────────────────────────────────────────────────────────
AUTH_BASE = "https://auth.openai.com"
PLATFORM_BASE = "https://platform.openai.com"
PLATFORM_OAUTH_CLIENT_ID = "app_2SKx67EdpoN0G6j64rFvigXD"
PLATFORM_OAUTH_REDIRECT_URI = f"{PLATFORM_BASE}/auth/callback"
PLATFORM_OAUTH_AUDIENCE = "https://api.openai.com/v1"
PLATFORM_AUTH0_CLIENT = "eyJuYW1lIjoiYXV0aDAtc3BhLWpzIiwidmVyc2lvbiI6IjEuMjEuMCJ9"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODEX_OAUTH_SCOPE = "openid email profile offline_access"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Google Chrome";v="145", "Not?A_Brand";v="8", "Chromium";v="145"'
SEC_CH_UA_FULL_VERSION_LIST = (
    '"Chromium";v="145.0.0.0", "Not:A-Brand";v="99.0.0.0", "Google Chrome";v="145.0.0.0"'
)

COMMON_HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": AUTH_BASE,
    "priority": "u=1, i",
    "user-agent": USER_AGENT,
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-arch": '"x86_64"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version-list": SEC_CH_UA_FULL_VERSION_LIST,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": '""',
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"10.0.0"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

NAVIGATE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": USER_AGENT,
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-arch": '"x86_64"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version-list": SEC_CH_UA_FULL_VERSION_LIST,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": '""',
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"10.0.0"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


# ── 辅助函数 ─────────────────────────────────────────────────────────
class UsernameAlreadyExistsError(RuntimeError):
    """邮箱已被注册"""
    pass


def _generate_pkce() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _random_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    value = list(
        secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.ascii_lowercase)
        + secrets.choice(string.digits)
        + secrets.choice("!@#$%")
        + "".join(secrets.choice(chars) for _ in range(max(0, length - 4)))
    )
    random.shuffle(value)
    return "".join(value)


def _random_name() -> tuple[str, str]:
    return random.choice(["James", "Robert", "John", "Michael", "David", "Mary", "Emma", "Olivia"]), random.choice(
        ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
    )


def _random_birthdate() -> str:
    return f"{random.randint(1996, 2006):04d}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _default_token_oauth(profile: str = "platform") -> dict[str, str]:
    if str(profile or "").strip().lower() == "platform":
        return {
            "profile": "platform",
            "auth_base": AUTH_BASE,
            "authorize_path": "/api/accounts/authorize",
            "client_id": PLATFORM_OAUTH_CLIENT_ID,
            "redirect_uri": PLATFORM_OAUTH_REDIRECT_URI,
            "scope": "openid profile email offline_access",
            "audience": PLATFORM_OAUTH_AUDIENCE,
            "auth0_client": PLATFORM_AUTH0_CLIENT,
        }
    return {
        "profile": "codex",
        "auth_base": AUTH_BASE,
        "authorize_path": "/oauth/authorize",
        "client_id": CODEX_OAUTH_CLIENT_ID,
        "redirect_uri": CODEX_OAUTH_REDIRECT_URI,
        "scope": CODEX_OAUTH_SCOPE,
    }


def _normalize_token_oauth(oauth: dict[str, Any] | None, profile: str = "platform") -> dict[str, str]:
    result = _default_token_oauth(profile)
    if isinstance(oauth, dict):
        for key in ("auth_base", "authorize_path", "client_id", "redirect_uri", "scope", "audience", "auth0_client"):
            value = str(oauth.get(key) or "").strip()
            if value:
                result[key] = value
    return result


def _response_json(resp: Any) -> dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _make_trace_headers() -> dict[str, str]:
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    return {
        "traceparent": f"00-{uuid.uuid4().hex}-{format(int(parent_id), '016x')}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    }


def _request_with_retry(session: Any, method: str, url: str, retry_attempts: int = 3, **kwargs: Any) -> tuple[Any | None, str]:
    last_error = ""
    timeout = kwargs.setdefault("timeout", 30)
    attempts = 1 if getattr(session, "_local_retry_installed", False) else max(1, max(retry_attempts, LOCAL_RETRY_ATTEMPTS))
    for index in range(attempts):
        if index > 0 and isinstance(timeout, (int, float)):
            kwargs["timeout"] = timeout + 10
        try:
            return session.request(method.upper(), url, **kwargs), ""
        except Exception as error:
            if not is_local_retryable_error(error):
                return None, str(error)
            last_error = str(error)
            time.sleep(1)
    return None, last_error


def create_session(proxy: str = "") -> Any:
    session: Any = install_local_retry(curl_requests.Session(impersonate="chrome", http_version=get_curl_http_version()))
    session.verify = False
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


# ── 邮件 Provider (从模块导入) ───────────────────────────────────────
from .mail_provider import create_mailbox, wait_for_code

# ── Sentinel Token ───────────────────────────────────────────────────
from .sentinel import build_sentinel_token

# 调试事件
_OAUTH_DEBUG: list[dict[str, Any]] = []


def _debug_event(event: str, **kwargs: Any) -> None:
    item = {"event": event, **kwargs}
    _OAUTH_DEBUG.append(item)
    del _OAUTH_DEBUG[:-30]


def oauth_debug_events() -> list[dict[str, Any]]:
    return list(_OAUTH_DEBUG)


# ── OAuth 回调处理 ──────────────────────────────────────────────────
def _extract_oauth_callback_params(url: str) -> dict[str, str] | None:
    if not url:
        return None
    try:
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(url).query)
    except Exception:
        return None
    code = str((params.get("code") or [""])[0]).strip()
    if not code:
        return None
    return {"code": code, "state": str((params.get("state") or [""])[0]).strip()}


def _follow_redirects_for_callback(
    session: Any, url: str, headers: dict[str, str] | None = None, max_hops: int = 10
) -> dict[str, str] | None:
    if not url:
        return None
    current_url = f"{AUTH_BASE}{url}" if url.startswith("/") else url
    request_headers = headers or NAVIGATE_HEADERS
    for _ in range(max_hops):
        response, error = _request_with_retry(
            session, "get", current_url, headers=request_headers, allow_redirects=False
        )
        if response is None:
            _debug_event("follow_redirect_error", url=current_url[:300], error=error[:500])
            break
        _debug_event(
            "follow_redirect",
            url=current_url[:300],
            status=getattr(response, "status_code", None),
            location=str(response.headers.get("Location") or "")[:300],
        )
        callback_params = _extract_oauth_callback_params(str(response.url)) or _extract_oauth_callback_params(
            str(response.headers.get("Location") or "").strip()
        )
        if callback_params:
            return callback_params
        data = _response_json(response)
        continue_url = str(data.get("continue_url") or "").strip() if isinstance(data, dict) else ""
        if continue_url:
            current_url = urljoin(current_url, continue_url)
            continue
        location = str(response.headers.get("Location") or "").strip()
        if response.status_code not in (301, 302, 303, 307, 308) or not location:
            break
        current_url = urljoin(current_url, location)
    return None


def _extract_oauth_params_from_consent(
    session: Any, consent_url: str, device_id: str
) -> dict[str, str] | None:
    """从 OAuth 授权确认页面提取回调参数"""
    if consent_url.startswith("/"):
        consent_url = f"{AUTH_BASE}{consent_url}"
    callback_params = _follow_redirects_for_callback(session, consent_url, NAVIGATE_HEADERS)
    if callback_params:
        return callback_params
    raw = session.cookies.get("oai-client-auth-session", domain=".auth.openai.com") or session.cookies.get("oai-client-auth-session")
    if not raw:
        return None
    try:
        first_part = raw.split(".")[0]
        padding = 4 - len(first_part) % 4
        if padding != 4:
            first_part += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(first_part))
        workspace_id = payload["workspaces"][0]["id"]
    except Exception:
        return None
    headers = dict(COMMON_HEADERS)
    headers["referer"] = consent_url
    headers["oai-device-id"] = device_id
    headers.update(_make_trace_headers())
    ws_resp = session.post(
        f"{AUTH_BASE}/api/accounts/workspace/select",
        json={"workspace_id": workspace_id},
        headers=headers,
        allow_redirects=False,
        timeout=30,
    )
    _debug_event(
        "workspace_select",
        status=getattr(ws_resp, "status_code", None),
        location=str(ws_resp.headers.get("Location") or "")[:300],
    )
    callback_params = _extract_oauth_callback_params(str(ws_resp.headers.get("Location") or "").strip())
    if callback_params:
        return callback_params
    ws_data = _response_json(ws_resp)
    ws_continue_url = str(ws_data.get("continue_url") or "").strip() if isinstance(ws_data, dict) else ""
    if ws_continue_url:
        callback_params = _follow_redirects_for_callback(session, urljoin(consent_url, ws_continue_url))
        if callback_params:
            return callback_params
    orgs = ((ws_data.get("data") or {}).get("orgs") or []) if isinstance(ws_data, dict) else []
    if not orgs:
        return None
    org_id = str((orgs[0] or {}).get("id") or "").strip()
    project_id = str(((orgs[0] or {}).get("projects") or [{}])[0].get("id") or "").strip()
    if not org_id:
        return None
    org_headers = dict(COMMON_HEADERS)
    org_headers["referer"] = str(ws_data.get("continue_url") or consent_url)
    org_headers["oai-device-id"] = device_id
    org_headers.update(_make_trace_headers())
    body: dict[str, str] = {"org_id": org_id}
    if project_id:
        body["project_id"] = project_id
    org_resp = session.post(
        f"{AUTH_BASE}/api/accounts/organization/select",
        json=body,
        headers=org_headers,
        allow_redirects=False,
        timeout=30,
    )
    _debug_event(
        "organization_select",
        status=getattr(org_resp, "status_code", None),
        location=str(org_resp.headers.get("Location") or "")[:300],
    )
    callback_params = _extract_oauth_callback_params(str(org_resp.headers.get("Location") or "").strip())
    if callback_params:
        return callback_params
    org_data = _response_json(org_resp)
    org_continue_url = str(org_data.get("continue_url") or "").strip() if isinstance(org_data, dict) else ""
    if org_continue_url:
        return _follow_redirects_for_callback(session, urljoin(consent_url, org_continue_url))
    return None


# ── PlatformRegistrar ────────────────────────────────────────────────
class PlatformRegistrar:
    """OpenAI 平台自动注册器 - 7步完整注册流程"""

    def __init__(self, proxy: str = "", token_oauth: dict[str, Any] | None = None, fixed_password: str = "") -> None:
        self.session = create_session(proxy)
        self.device_id = str(uuid.uuid4())
        self.token_oauth = _normalize_token_oauth(token_oauth)
        self.fixed_password = str(fixed_password or "").strip()

    def close(self) -> None:
        self.session.close()

    def _json_headers(self, referer: str) -> dict[str, str]:
        headers = dict(COMMON_HEADERS)
        headers["referer"] = referer
        headers["oai-device-id"] = self.device_id
        headers.update(_make_trace_headers())
        return headers

    def _platform_authorize(self, email: str) -> None:
        """步骤2: 初始化 Platform OAuth 授权"""
        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")
        _, code_challenge = _generate_pkce()
        params = {
            "issuer": AUTH_BASE,
            "client_id": PLATFORM_OAUTH_CLIENT_ID,
            "audience": PLATFORM_OAUTH_AUDIENCE,
            "redirect_uri": PLATFORM_OAUTH_REDIRECT_URI,
            "device_id": self.device_id,
            "screen_hint": "login_or_signup",
            "max_age": "0",
            "login_hint": email,
            "scope": "openid profile email offline_access",
            "response_type": "code",
            "response_mode": "query",
            "state": secrets.token_urlsafe(32),
            "nonce": secrets.token_urlsafe(32),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "auth0Client": PLATFORM_AUTH0_CLIENT,
        }
        from urllib.parse import urlencode
        resp, error = _request_with_retry(
            self.session, "get",
            f"{AUTH_BASE}/api/accounts/authorize?{urlencode(params)}",
            headers={**NAVIGATE_HEADERS, "referer": f"{PLATFORM_BASE}/"},
            allow_redirects=True,
        )
        if resp is None or resp.status_code != 200:
            err = _response_json(resp).get("error", {}) if resp is not None else {}
            detail = f": {err.get('code', '')} - {err.get('message', '')}".strip(" -") if err else ""
            raise RuntimeError(error or f"platform_authorize_http_{getattr(resp, 'status_code', 'unknown')}{detail}")

    def _register_user(self, email: str, password: str) -> None:
        """步骤3: 注册用户"""
        headers = self._json_headers(f"{AUTH_BASE}/create-account/password")
        headers["openai-sentinel-token"] = build_sentinel_token(self.session, self.device_id, "username_password_create")
        resp, error = _request_with_retry(
            self.session, "post",
            f"{AUTH_BASE}/api/accounts/user/register",
            json={"username": email, "password": password},
            headers=headers,
        )
        if resp is None or resp.status_code != 200:
            data = _response_json(resp) if resp is not None else {}
            err_info = data.get("error") if isinstance(data.get("error"), dict) else {}
            if err_info.get("code") == "username_already_exists":
                raise UsernameAlreadyExistsError(email)
            detail = f", detail={json.dumps(data, ensure_ascii=False)}" if data else ""
            raise RuntimeError(error or f"user_register_http_{getattr(resp, 'status_code', 'unknown')}{detail}")

    def _send_otp(self) -> None:
        """步骤4: 发送验证码"""
        resp, error = _request_with_retry(
            self.session, "get",
            f"{AUTH_BASE}/api/accounts/email-otp/send",
            headers={**NAVIGATE_HEADERS, "referer": f"{AUTH_BASE}/create-account/password"},
            allow_redirects=True,
        )
        if resp is None or resp.status_code not in (200, 302):
            raise RuntimeError(error or f"send_otp_http_{getattr(resp, 'status_code', 'unknown')}")

    def _validate_otp(self, code: str) -> None:
        """步骤6: 验证OTP"""
        headers = self._json_headers(f"{AUTH_BASE}/email-verification")
        resp, error = _request_with_retry(
            self.session, "post",
            f"{AUTH_BASE}/api/accounts/email-otp/validate",
            json={"code": code},
            headers=headers,
        )
        if resp is None or resp.status_code != 200:
            headers["openai-sentinel-token"] = build_sentinel_token(self.session, self.device_id, "authorize_continue")
            resp, error = _request_with_retry(
                self.session, "post",
                f"{AUTH_BASE}/api/accounts/email-otp/validate",
                json={"code": code},
                headers=headers,
            )
        if resp is None or resp.status_code != 200:
            body = ""
            try:
                body = (resp.text or "")[:500] if resp is not None else ""
            except Exception:
                pass
            raise RuntimeError(error or f"validate_otp_http_{getattr(resp, 'status_code', 'unknown')}_body={body}")

    def _create_account(self, name: str, birthdate: str) -> None:
        """步骤6: 创建账号个人信息"""
        headers = self._json_headers(f"{AUTH_BASE}/about-you")
        headers["openai-sentinel-token"] = build_sentinel_token(self.session, self.device_id, "oauth_create_account")
        resp, error = _request_with_retry(
            self.session, "post",
            f"{AUTH_BASE}/api/accounts/create_account",
            json={"name": name, "birthdate": birthdate},
            headers=headers,
        )
        if resp is None or resp.status_code not in (200, 302):
            detail = f", detail={json.dumps(_response_json(resp), ensure_ascii=False)}" if resp is not None else ""
            raise RuntimeError(error or f"create_account_http_{getattr(resp, 'status_code', 'unknown')}{detail}")

    def _login_and_exchange_tokens(
        self, email: str, password: str, mailbox: dict[str, Any], mail_config: dict[str, Any], proxy: str
    ) -> dict[str, Any]:
        """步骤7: 登录并完成OAuth流程，换取 access_token + refresh_token + id_token"""
        login_session = create_session(proxy)
        login_device_id = str(uuid.uuid4())
        login_session.cookies.set("oai-did", login_device_id, domain=".auth.openai.com")
        login_session.cookies.set("oai-did", login_device_id, domain="auth.openai.com")
        code_verifier, code_challenge = _generate_pkce()
        oauth = self.token_oauth
        authorize_path = str(oauth.get("authorize_path") or "/oauth/authorize").strip()
        _debug_event(
            "token_oauth",
            profile=str(oauth.get("profile") or ""),
            client_id=str(oauth.get("client_id") or ""),
            authorize_path=authorize_path,
            redirect_uri=str(oauth.get("redirect_uri") or ""),
        )
        params = {
            "client_id": oauth["client_id"],
            "redirect_uri": oauth["redirect_uri"],
            "device_id": login_device_id,
            "screen_hint": "login_or_signup",
            "max_age": "0",
            "login_hint": email,
            "scope": oauth["scope"],
            "response_type": "code",
            "response_mode": "query",
            "state": secrets.token_urlsafe(32),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if authorize_path == "/api/accounts/authorize":
            params["issuer"] = AUTH_BASE
            params["audience"] = str(oauth.get("audience") or PLATFORM_OAUTH_AUDIENCE)
            params["nonce"] = secrets.token_urlsafe(32)
            params["auth0Client"] = str(oauth.get("auth0_client") or PLATFORM_AUTH0_CLIENT)
        else:
            params["prompt"] = "login"
            params["id_token_add_organizations"] = "true"
            params["codex_cli_simplified_flow"] = "true"
        from urllib.parse import urlencode

        def _login_json_headers(referer: str) -> dict[str, str]:
            h = dict(COMMON_HEADERS)
            h["referer"] = referer
            h["oai-device-id"] = login_device_id
            h.update(_make_trace_headers())
            return h

        resp, error = _request_with_retry(
            login_session, "get",
            f"{AUTH_BASE}{authorize_path}?{urlencode(params)}",
            headers={**NAVIGATE_HEADERS, "referer": f"{PLATFORM_BASE}/"},
            allow_redirects=True,
        )
        if resp is None:
            raise RuntimeError(error or "platform_login_authorize_failed")

        def _do_authorize_continue() -> tuple[Any | None, str]:
            h = _login_json_headers(f"{AUTH_BASE}/log-in?usernameKind=email")
            h["openai-sentinel-token"] = build_sentinel_token(login_session, login_device_id, "authorize_continue")
            return _request_with_retry(
                login_session, "post",
                f"{AUTH_BASE}/api/accounts/authorize/continue",
                json={"username": {"kind": "email", "value": email}},
                headers=h,
                allow_redirects=False,
            )

        resp, error = _do_authorize_continue()
        if resp is not None and resp.status_code == 409:
            for cookie in list(login_session.cookies):
                if "auth.openai.com" in getattr(cookie, "domain", ""):
                    login_session.cookies.clear(domain=cookie.domain, path=cookie.path, name=cookie.name)
            login_session.cookies.set("oai-did", login_device_id, domain=".auth.openai.com")
            login_session.cookies.set("oai-did", login_device_id, domain="auth.openai.com")
            resp, error = _request_with_retry(
                login_session, "get",
                f"{AUTH_BASE}{authorize_path}?{urlencode(params)}",
                headers={**NAVIGATE_HEADERS, "referer": f"{PLATFORM_BASE}/"},
                allow_redirects=True,
            )
            if resp is None:
                raise RuntimeError(error or "platform_login_authorize_retry_failed")
            resp, error = _do_authorize_continue()

        if resp is None or resp.status_code != 200:
            detail = json.dumps(_response_json(resp), ensure_ascii=False) if resp is not None else ""
            raise RuntimeError(error or f"email_submit_http_{getattr(resp, 'status_code', 'unknown')}" + (f": {detail}" if detail else ""))

        headers = _login_json_headers(f"{AUTH_BASE}/log-in/password")
        headers["openai-sentinel-token"] = build_sentinel_token(login_session, login_device_id, "password_verify")
        resp, error = _request_with_retry(
            login_session, "post",
            f"{AUTH_BASE}/api/accounts/password/verify",
            json={"password": password},
            headers=headers,
            allow_redirects=False,
        )
        if resp is None or resp.status_code != 200:
            body = ""
            try:
                body = (resp.text or "")[:500] if resp is not None else ""
            except Exception:
                pass
            login_session.close()
            raise RuntimeError(error or f"password_verify_http_{getattr(resp, 'status_code', '')}_body={body}")

        payload = _response_json(resp)
        continue_url = str(payload.get("continue_url") or "").strip()
        page_type = str(((payload.get("page") or {}).get("type")) or "")

        if page_type == "email_otp_verification" or "email-verification" in continue_url or "email-otp" in continue_url:
            code = wait_for_code(mail_config, mailbox)
            if not code:
                login_session.close()
                raise RuntimeError("login email OTP timeout")
            resp, reason = _request_with_retry(
                login_session, "post",
                f"{AUTH_BASE}/api/accounts/email-otp/validate",
                json={"code": code},
                headers=_login_json_headers(f"{AUTH_BASE}/email-verification"),
            )
            if resp is None or resp.status_code != 200:
                login_session.close()
                raise RuntimeError(reason or f"login_otp_validate_http_{getattr(resp, 'status_code', 'unknown')}")
            otp_payload = _response_json(resp)
            continue_url = str(otp_payload.get("continue_url") or continue_url).strip()

        if not continue_url:
            continue_url = f"{AUTH_BASE}/sign-in-with-chatgpt/codex/consent"

        callback_params = _extract_oauth_params_from_consent(login_session, continue_url, login_device_id)
        if not callback_params:
            try:
                r = login_session.get(continue_url, headers=NAVIGATE_HEADERS, allow_redirects=True, timeout=30)
                callback_params = _extract_oauth_callback_params(str(r.url))
                if not callback_params:
                    for hist in getattr(r, "history", []) or []:
                        loc = str(hist.headers.get("Location") or "")
                        callback_params = _extract_oauth_callback_params(loc)
                        if callback_params:
                            break
            except Exception:
                pass
        if not callback_params:
            login_session.close()
            raise RuntimeError("failed to extract OAuth code from consent flow")

        code = str(callback_params.get("code") or "").strip()
        if not code:
            login_session.close()
            raise RuntimeError("empty OAuth code")

        token_resp, error = _request_with_retry(
            create_session(proxy),
            "post",
            f"{AUTH_BASE}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": oauth["redirect_uri"],
                "client_id": oauth["client_id"],
                "code_verifier": code_verifier,
            },
            timeout=60,
        )
        login_session.close()
        if token_resp is None:
            raise RuntimeError(f"token exchange request failed: {error}")
        data = _response_json(token_resp)
        if token_resp.status_code != 200 or not data.get("access_token") or not data.get("refresh_token"):
            raise RuntimeError("token exchange failed")
        access_token = str(data.get("access_token") or "").strip()
        claims = _decode_jwt_payload(str(data.get("id_token") or "")) or _decode_jwt_payload(access_token)
        return {
            "email": str(claims.get("email") or email).strip(),
            "access_token": access_token,
            "refresh_token": str(data.get("refresh_token") or "").strip(),
            "id_token": str(data.get("id_token") or "").strip(),
            "oauth_profile": oauth.get("profile") or "",
            "oauth_client_id": oauth["client_id"],
            "oauth_scope": oauth["scope"],
        }

    def register(self, mail_config: dict[str, Any], proxy: str, log_callback=None) -> dict[str, Any]:
        """完整注册流程，支持日志回调"""
        last_error: str | None = None
        for attempt in range(5):
            try:
                self.session.close()
                self.session = create_session(proxy)
                self.device_id = str(uuid.uuid4())
                return self._register_once(mail_config, proxy, log_callback)
            except UsernameAlreadyExistsError as exc:
                email = exc.args[0] if exc.args else "?"
                last_error = f"邮箱 {email} 已被注册 (第{attempt + 1}/5次), 换邮箱重试..."
                if log_callback:
                    log_callback(last_error, "yellow")
        raise RuntimeError(last_error or "registration failed after 5 attempts")

    def _register_once(self, mail_config: dict[str, Any], proxy: str, log_callback=None) -> dict[str, Any]:
        """执行单次完整的7步注册流程"""

        def log(msg: str, color: str = "info") -> None:
            if log_callback:
                log_callback(msg, color)

        log("[1/7] 创建临时邮箱...", "info")
        mailbox = create_mailbox(mail_config)
        email = str(mailbox.get("address") or "").strip()
        if not email:
            raise RuntimeError("mailbox missing address")
        log(f"      邮箱: {email}", "info")
        password = self.fixed_password or _random_password()
        first_name, last_name = _random_name()

        log("[2/7] 初始化 OAuth 授权...", "info")
        self._platform_authorize(email)

        log("[3/7] 注册账号并设置密码...", "info")
        self._register_user(email, password)

        log("[4/7] 发送验证码...", "info")
        self._send_otp()

        log("[5/7] 等待验证码...", "info")
        code = wait_for_code(mail_config, mailbox)
        if not code:
            raise RuntimeError("registration OTP timeout")
        log(f"      验证码: {code}", "green")

        log("[6/7] 校验验证码并创建账号...", "info")
        self._validate_otp(code)
        self._create_account(f"{first_name} {last_name}", _random_birthdate())

        log("[7/7] 登录换取 Token...", "info")
        tokens = self._login_and_exchange_tokens(email, password, mailbox, mail_config, proxy)
        log(f"      完成! refresh_token={'有' if tokens.get('refresh_token') else '无'}", "green")
        return {
            "email": email,
            "password": password,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "id_token": tokens["id_token"],
            "oauth_profile": tokens.get("oauth_profile") or "",
            "oauth_client_id": tokens.get("oauth_client_id") or "",
            "oauth_scope": tokens.get("oauth_scope") or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


def auto_register(
    mail_config: dict[str, Any],
    proxy: str = "",
    token_oauth: dict[str, Any] | None = None,
    fixed_password: str = "",
    log_callback=None,
) -> dict[str, Any]:
    """便捷函数: 创建注册器并执行注册"""
    registrar = PlatformRegistrar(proxy, token_oauth=token_oauth, fixed_password=fixed_password)
    try:
        return registrar.register(mail_config, proxy, log_callback)
    finally:
        registrar.close()
