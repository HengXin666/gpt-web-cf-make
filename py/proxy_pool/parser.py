"""代理池订阅解析器 - 支持 Clash YAML / Base64 / 单 URI 解析"""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs

from .models import ProxyNode


def parse_subscription(raw: str, sub_type: str = "auto") -> list[ProxyNode]:
    """自动检测格式并解析订阅内容，返回 ProxyNode 列表。"""
    raw = (raw or "").strip()
    if not raw:
        return []

    if sub_type == "clash_yaml" or (sub_type == "auto" and _looks_like_clash_yaml(raw)):
        return parse_clash_yaml(raw)
    if sub_type == "base64" or sub_type == "auto":
        nodes = parse_base64_node_list(raw)
        if nodes:
            return nodes
    # fallback: 逐行尝试 URI
    if sub_type == "auto":
        return _parse_line_separated(raw)
    return []


def _looks_like_clash_yaml(raw: str) -> bool:
    """检测是否为 Clash YAML 格式。"""
    return "proxies:" in raw[:2000] or "Proxy:" in raw[:2000]


# ── Clash YAML 解析 ──────────────────────────────────────────────

def parse_clash_yaml(raw_yaml: str) -> list[ProxyNode]:
    """解析 Clash YAML proxies 列表。"""
    try:
        import yaml  # type: ignore[import-untyped]
        data = yaml.safe_load(raw_yaml)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    proxies = data.get("proxies") or data.get("Proxy") or []
    if not isinstance(proxies, list):
        return []

    nodes: list[ProxyNode] = []
    for item in proxies:
        if not isinstance(item, dict):
            continue
        node = _clash_proxy_to_node(item)
        if node:
            nodes.append(node)
    return nodes


def _clash_proxy_to_node(item: dict[str, Any]) -> ProxyNode | None:
    """将单个 Clash proxy dict 转为 ProxyNode。"""
    ptype = str(item.get("type") or "").strip().lower()
    name = str(item.get("name") or item.get("remarks") or "").strip()
    server = str(item.get("server") or "").strip()
    port = int(item.get("port") or 0)

    if not server or not port or not ptype:
        return None

    node = ProxyNode(
        name=name,
        protocol=_normalize_protocol(ptype),
        server=server,
        port=port,
    )

    if ptype in ("http", "https"):
        node.username = str(item.get("username") or "")
        node.password = str(item.get("password") or "")
        node.proxy_url = _build_url(node.protocol, node.server, node.port, node.username, node.password)

    elif ptype == "socks5":
        node.username = str(item.get("username") or "")
        node.password = str(item.get("password") or "")
        node.proxy_url = _build_url("socks5", node.server, node.port, node.username, node.password)

    elif ptype in ("ss", "shadowsocks"):
        cipher = str(item.get("cipher") or item.get("method") or "")
        password = str(item.get("password") or "")
        node.extra = {"method": cipher, "password": password}
        plugin = item.get("plugin")
        if plugin:
            node.extra["plugin"] = plugin
            plugin_opts = item.get("plugin-opts") or {}
            if isinstance(plugin_opts, dict):
                node.extra["plugin_opts"] = plugin_opts
        node.proxy_url = _build_ss_url(cipher, password, node.server, node.port)

    elif ptype == "vmess":
        node.extra = {
            "uuid": str(item.get("uuid") or ""),
            "alterId": int(item.get("alterId") or item.get("alter_id") or 0),
            "security": str(item.get("cipher") or item.get("security") or "auto"),
            "network": str(item.get("network") or "tcp"),
        }
        # TLS
        tls = item.get("tls")
        if tls:
            node.extra["tls"] = True
            node.extra["sni"] = str(item.get("servername") or item.get("sni") or "")
            node.extra["skip_cert_verify"] = bool(item.get("skip-cert-verify") or False)
        # WS
        ws_opts = item.get("ws-opts") or item.get("ws_opts")
        if isinstance(ws_opts, dict):
            node.extra["ws_path"] = str(ws_opts.get("path") or "")
            headers = ws_opts.get("headers") or {}
            if isinstance(headers, dict):
                node.extra["ws_host"] = str(headers.get("Host") or headers.get("host") or "")
        node.proxy_url = _build_vmess_url(node)

    elif ptype == "trojan":
        password = str(item.get("password") or "")
        sni = str(item.get("sni") or item.get("servername") or "")
        node.extra = {
            "password": password,
            "sni": sni,
            "skip_cert_verify": bool(item.get("skip-cert-verify") or False),
        }
        node.proxy_url = _build_trojan_url(password, node.server, node.port, sni)

    elif ptype == "hysteria" or ptype == "hysteria2" or ptype == "tuic":
        # 这些协议也存储但 proxy_url 为空
        node.extra = {k: v for k, v in item.items() if k not in ("type", "name", "server", "port")}
        node.proxy_url = ""

    elif ptype in ("ssr", "shadowsocksr"):
        node.extra = {k: v for k, v in item.items() if k not in ("type", "name", "server", "port")}
        node.proxy_url = ""

    else:
        # 未知协议，仍创建节点
        node.extra = {k: v for k, v in item.items() if k not in ("type", "name", "server", "port")}
        node.proxy_url = ""

    return node


# ── Base64 解码 + 逐行 URI ─────────────────────────────────────

def parse_base64_node_list(raw_b64: str) -> list[ProxyNode]:
    """解码 base64 并逐行解析代理 URI。"""
    raw_b64 = (raw_b64 or "").strip()
    if not raw_b64:
        return []
    try:
        decoded = base64.b64decode(raw_b64).decode("utf-8", errors="replace")
    except Exception:
        # 可能不是 base64
        return []
    return _parse_line_separated(decoded)


def _parse_line_separated(text: str) -> list[ProxyNode]:
    """逐行解析代理 URI。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    nodes: list[ProxyNode] = []
    for line in lines:
        node = parse_single_uri(line)
        if node:
            nodes.append(node)
    return nodes


# ── 单 URI 解析 ──────────────────────────────────────────────────

def parse_single_uri(uri: str) -> ProxyNode | None:
    """解析单个代理 URI 为 ProxyNode。"""
    uri = (uri or "").strip()
    if not uri:
        return None

    # ss://
    if uri.startswith("ss://"):
        return _parse_ss_uri(uri)
    # vmess://
    if uri.startswith("vmess://"):
        return _parse_vmess_uri(uri)
    # trojan://
    if uri.startswith("trojan://"):
        return _parse_trojan_uri(uri)
    # socks5://
    if uri.startswith("socks5://"):
        return _parse_generic_uri(uri, "socks5")
    # http:// / https://
    if uri.startswith("http://"):
        return _parse_generic_uri(uri, "http")
    if uri.startswith("https://"):
        return _parse_generic_uri(uri, "https")
    # ssr://
    if uri.startswith("ssr://"):
        return _parse_ssr_uri(uri)
    # vless://
    if uri.startswith("vless://"):
        return _parse_vless_uri(uri)
    # hysteria2:// or hy2://
    if uri.startswith("hysteria2://") or uri.startswith("hy2://"):
        return _parse_hysteria2_uri(uri)
    # hysteria:// or hysteria1://
    if uri.startswith("hysteria://") or uri.startswith("hysteria1://"):
        return _parse_hysteria_uri(uri)
    # tuic://
    if uri.startswith("tuic://"):
        return _parse_tuic_uri(uri)
    # wg:// (WireGuard)
    if uri.startswith("wg://"):
        return _parse_wg_uri(uri)

    return None


def _parse_generic_uri(uri: str, protocol: str) -> ProxyNode | None:
    """解析 http/https/socks5 URI。"""
    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    server = parsed.hostname or ""
    port = parsed.port or 0
    if not server or not port:
        return None

    name = unquote(parsed.fragment) if parsed.fragment else f"{server}:{port}"
    username = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else ""

    node = ProxyNode(
        name=name,
        protocol=protocol,
        server=server,
        port=port,
        username=username,
        password=password,
        proxy_url=_build_url(protocol, server, port, username, password),
    )
    return node


def _parse_ss_uri(uri: str) -> ProxyNode | None:
    """解析 ss:// URI（SIP002 和 legacy 格式）。"""
    uri = uri.strip()
    fragment = ""
    if "#" in uri:
        uri, fragment = uri.rsplit("#", 1)
        fragment = unquote(fragment)

    # SIP002: ss://base64(method:password)@host:port
    # 或 ss://base64(method:password@host:port)  (legacy)
    body = uri[5:]  # 去掉 ss://

    if "@" in body:
        # SIP002 格式
        try:
            at_idx = body.rindex("@")
            userinfo_b64 = body[:at_idx]
            host_port = body[at_idx + 1:]

            # 解码 userinfo
            userinfo_b64 += "=" * (-len(userinfo_b64) % 4)
            userinfo = base64.b64decode(userinfo_b64).decode("utf-8", errors="replace")

            if ":" not in userinfo:
                return None
            method, password = userinfo.split(":", 1)

            parsed_hp = urlparse(f"//{host_port}")
            server = parsed_hp.hostname or ""
            port = parsed_hp.port or 0
            if not server or not port:
                return None

            name = fragment or f"{server}:{port}"
            return ProxyNode(
                name=name,
                protocol="ss",
                server=server,
                port=port,
                extra={"method": method, "password": password},
                proxy_url=_build_ss_url(method, password, server, port),
            )
        except Exception:
            pass

    # Legacy 格式: ss://base64(method:password@host:port)
    try:
        body += "=" * (-len(body) % 4)
        decoded = base64.b64decode(body).decode("utf-8", errors="replace")

        if "@" not in decoded or ":" not in decoded:
            return None

        userinfo, host_port = decoded.rsplit("@", 1)
        if ":" not in userinfo:
            return None
        method, password = userinfo.split(":", 1)

        if ":" not in host_port:
            return None
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str) if port_str.isdigit() else 0
        if not host or not port:
            return None

        name = fragment or f"{host}:{port}"
        return ProxyNode(
            name=name,
            protocol="ss",
            server=host,
            port=port,
            extra={"method": method, "password": password},
            proxy_url=_build_ss_url(method, password, host, port),
        )
    except Exception:
        return None


def _parse_vmess_uri(uri: str) -> ProxyNode | None:
    """解析 vmess:// URI（base64 JSON）。"""
    body = uri[8:]  # 去掉 vmess://
    # 去掉可能的查询参数
    if "?" in body:
        body = body.split("?", 1)[0]
    try:
        body += "=" * (-len(body) % 4)
        data = json.loads(base64.b64decode(body).decode("utf-8", errors="replace"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    server = str(data.get("add") or data.get("address") or "").strip()
    port = int(data.get("port") or data.get("port") or 0)
    if not server or not port:
        return None

    name = str(data.get("ps") or data.get("remarks") or f"{server}:{port}")
    uuid_str = str(data.get("id") or "")
    alter_id = int(data.get("aid") or data.get("alterId") or 0)
    security = str(data.get("scy") or data.get("security") or "auto")
    network = str(data.get("net") or "tcp")
    tls_enabled = str(data.get("tls") or "").lower() == "tls"
    sni = str(data.get("sni") or data.get("host") or "")
    path = str(data.get("path") or "")

    node = ProxyNode(
        name=name,
        protocol="vmess",
        server=server,
        port=port,
        extra={
            "uuid": uuid_str,
            "alterId": alter_id,
            "security": security,
            "network": network,
            "tls": tls_enabled,
            "sni": sni,
            "ws_path": path,
            "ws_host": str(data.get("host") or ""),
        },
        proxy_url="",  # vmess 需要本地客户端
    )
    return node


def _parse_trojan_uri(uri: str) -> ProxyNode | None:
    """解析 trojan:// URI。"""
    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    password = unquote(parsed.username) if parsed.username else ""
    server = parsed.hostname or ""
    port = parsed.port or 0
    if not server or not port:
        return None

    params = parse_qs(parsed.query)
    sni = params.get("sni", [""])[0] or server
    skip_cert = params.get("allowInsecure", ["0"])[0] in ("1", "true")
    name = unquote(parsed.fragment) if parsed.fragment else f"{server}:{port}"

    node = ProxyNode(
        name=name,
        protocol="trojan",
        server=server,
        port=port,
        extra={
            "password": password,
            "sni": sni,
            "skip_cert_verify": skip_cert,
        },
        proxy_url="",  # trojan 需要本地客户端
    )
    return node


def _parse_ssr_uri(uri: str) -> ProxyNode | None:
    """解析 ssr:// URI（基本提取）。"""
    body = uri[6:]  # 去掉 ssr://
    try:
        body += "=" * (-len(body) % 4)
        decoded = base64.b64decode(body).decode("utf-8", errors="replace")
        # 格式: server:port:protocol:method:obfs:password_base64/?params
        parts = decoded.split(":")
        if len(parts) < 6:
            return None
        server = parts[0]
        port = int(parts[1]) if parts[1].isdigit() else 0
        protocol = parts[2]
        method = parts[3]
        obfs = parts[4]

        return ProxyNode(
            name=f"{server}:{port}",
            protocol="ssr",
            server=server,
            port=port,
            extra={"protocol": protocol, "method": method, "obfs": obfs},
            proxy_url="",
        )
    except Exception:
        return None


def _parse_vless_uri(uri: str) -> ProxyNode | None:
    """解析 vless:// URI。"""
    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    uuid_str = unquote(parsed.username) if parsed.username else ""
    server = parsed.hostname or ""
    port = parsed.port or 0
    if not server or not port:
        return None

    params = parse_qs(parsed.query)
    name = unquote(parsed.fragment) if parsed.fragment else f"{server}:{port}"

    def _p(key: str, default: str = "") -> str:
        vals = params.get(key, [])
        return vals[0] if vals else default

    node = ProxyNode(
        name=name,
        protocol="vless",
        server=server,
        port=port,
        extra={
            "uuid": uuid_str,
            "flow": _p("flow"),
            "security": _p("security", "none"),
            "encryption": _p("encryption", "none"),
            "type": _p("type", "tcp"),
            "host": _p("host"),
            "path": unquote(_p("path")),
            "headerType": _p("headerType"),
            "serviceName": _p("serviceName"),
            "sni": _p("sni"),
            "fp": _p("fp"),
            "pbk": _p("pbk"),
            "sid": _p("sid"),
            "quicSecurity": _p("quicSecurity"),
        },
        proxy_url="",  # vless 需要本地客户端
    )
    return node


def _parse_hysteria2_uri(uri: str) -> ProxyNode | None:
    """解析 hysteria2:// 或 hy2:// URI。"""
    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    password = unquote(parsed.username) if parsed.username else ""
    server = parsed.hostname or ""
    port = parsed.port or 0
    if not server or not port:
        return None

    params = parse_qs(parsed.query)
    name = unquote(parsed.fragment) if parsed.fragment else f"{server}:{port}"

    def _p(key: str, default: str = "") -> str:
        vals = params.get(key, [])
        return vals[0] if vals else default

    node = ProxyNode(
        name=name,
        protocol="hysteria2",
        server=server,
        port=port,
        password=password,
        extra={
            "sni": _p("sni", server),
            "insecure": _p("insecure", "0") in ("1", "true"),
            "obfs": _p("obfs"),
            "obfs_password": _p("obfs-password", _p("obfs_password")),
            "pin_sha256": _p("pinSHA256"),
            "mport": _p("mport"),
        },
        proxy_url="",  # hysteria2 需要本地客户端
    )
    return node


def _parse_hysteria_uri(uri: str) -> ProxyNode | None:
    """解析 hysteria:// 或 hysteria1:// URI。"""
    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    server = parsed.hostname or ""
    port = parsed.port or 0
    if not server or not port:
        return None

    params = parse_qs(parsed.query)
    name = unquote(parsed.fragment) if parsed.fragment else f"{server}:{port}"

    def _p(key: str, default: str = "") -> str:
        vals = params.get(key, [])
        return vals[0] if vals else default

    node = ProxyNode(
        name=name,
        protocol="hysteria",
        server=server,
        port=port,
        extra={
            "protocol": _p("protocol", "udp"),
            "obfs": _p("obfs"),
            "auth": _p("auth"),
            "auth_str": _p("auth_str"),
            "insecure": _p("insecure", "0") in ("1", "true"),
            "sni": _p("sni", server),
            "mport": _p("mport"),
        },
        proxy_url="",
    )
    return node


def _parse_tuic_uri(uri: str) -> ProxyNode | None:
    """解析 tuic:// URI。"""
    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    userinfo = (parsed.username or "").split(":")
    uuid_str = userinfo[0] if userinfo else ""
    password = userinfo[1] if len(userinfo) > 1 else unquote(parsed.password or "")
    server = parsed.hostname or ""
    port = parsed.port or 0
    if not server or not port:
        return None

    params = parse_qs(parsed.query)
    name = unquote(parsed.fragment) if parsed.fragment else f"{server}:{port}"

    def _p(key: str, default: str = "") -> str:
        vals = params.get(key, [])
        return vals[0] if vals else default

    node = ProxyNode(
        name=name,
        protocol="tuic",
        server=server,
        port=port,
        extra={
            "uuid": uuid_str,
            "password": password,
            "sni": _p("sni", server),
            "insecure": _p("allow_insecure", "0") in ("1", "true"),
            "congestion_control": _p("congestion_control"),
            "udp_relay_mode": _p("udp_relay_mode"),
        },
        proxy_url="",
    )
    return node


def _parse_wg_uri(uri: str) -> ProxyNode | None:
    """解析 wg:// URI（WireGuard，基本提取）。"""
    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    server = parsed.hostname or ""
    port = parsed.port or 0
    if not server or not port:
        return None

    params = parse_qs(parsed.query)
    name = unquote(parsed.fragment) if parsed.fragment else f"{server}:{port}"

    node = ProxyNode(
        name=name,
        protocol="wg",
        server=server,
        port=port,
        extra={k: v[0] for k, v in params.items()},
        proxy_url="",
    )
    return node


# ── URL 构建工具 ─────────────────────────────────────────────────

def _normalize_protocol(ptype: str) -> str:
    """标准化协议名称。"""
    mapping = {
        "shadowsocks": "ss",
        "shadowsocksr": "ssr",
        "socks": "socks5",
        "socks5": "socks5",
        "hy2": "hysteria2",
        "hysteria1": "hysteria",
    }
    return mapping.get(ptype, ptype)


def _build_url(protocol: str, server: str, port: int, username: str = "", password: str = "") -> str:
    """构建 http/https/socks5 代理 URL。"""
    if username or password:
        auth = f"{_quote(username)}:{_quote(password)}@"
    else:
        auth = ""
    return f"{protocol}://{auth}{server}:{port}"


def _build_ss_url(method: str, password: str, server: str, port: int) -> str:
    """构建 ss:// URL（SIP002 格式）。"""
    userinfo = f"{method}:{password}"
    b64 = base64.b64encode(userinfo.encode()).decode().rstrip("=")
    return f"ss://{b64}@{server}:{port}"


def _build_vmess_url(node: ProxyNode) -> str:
    """构建 vmess:// URL。不直接可用于 curl_cffi，返回空。"""
    return ""


def _build_trojan_url(password: str, server: str, port: int, sni: str = "") -> str:
    """构建 trojan:// URL。不直接可用于 curl_cffi，返回空。"""
    return ""


def _quote(s: str) -> str:
    """URL 编码用户名/密码中的特殊字符。"""
    from urllib.parse import quote
    return quote(s, safe="")


# ── ProxyNode → 可用代理 URL ────────────────────────────────────

def proxy_node_to_url(node: ProxyNode) -> str:
    """将 ProxyNode 转为 curl_cffi 可用的代理 URL。

    仅 http/https/socks5 可直接使用。
    ss/vmess/trojan 需要本地 Clash/mihomo 中转。
    """
    if node.proxy_url:
        return node.proxy_url
    if node.protocol in ("http", "https", "socks5"):
        return _build_url(node.protocol, node.server, node.port, node.username, node.password)
    return ""
