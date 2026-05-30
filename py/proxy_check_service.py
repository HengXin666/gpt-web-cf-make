"""代理纯净度检测 — 流式逐项返回，无重试，短超时"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Generator

from curl_cffi import requests as curl_requests
from curl_cffi.const import CurlHttpVersion


AI_ENDPOINTS = [
    {"name": "ChatGPT Web", "url": "https://chatgpt.com/cdn-cgi/trace"},
    {"name": "OpenAI API", "url": "https://api.openai.com/v1/models"},
    {"name": "OpenAI Platform", "url": "https://platform.openai.com"},
    {"name": "Codex", "url": "https://chatgpt.com/backend-api/codex/status"},
    {"name": "Anthropic", "url": "https://api.anthropic.com"},
]
_AI_ORDER = {ep["name"]: i for i, ep in enumerate(AI_ENDPOINTS)}

GRADE = [(90,"pure"),(70,"clean"),(50,"moderate"),(25,"risky"),(0,"dirty")]

def _grade(s):
    for t,g in GRADE:
        if s>=t: return g
    return "dirty"

def _session(proxy=""):
    s = curl_requests.Session(impersonate="chrome", http_version=CurlHttpVersion.V2TLS)
    s.verify = False
    if proxy: s.proxies = {"http":proxy,"https":proxy}
    return s

def _get(s,url,timeout=5):
    try:
        r=s.get(url,timeout=timeout)
        return True,r.status_code,r.text[:500]
    except Exception as e:
        return False,0,str(e)[:200]

def _ev(step,data):
    return json.dumps({"step":step,**data},ensure_ascii=False)+"\n"


def check_proxy_purity_stream(proxy=""):
    s=_session(proxy)
    try:
        # ── 第1轮: IP + TLS 并发 ──
        with ThreadPoolExecutor(2) as ex:
            f_ip=ex.submit(_ip,s)
            f_tls=ex.submit(_tls,s)
            ip=f_ip.result()
            tls=f_tls.result()

        yield _ev("ip",ip)
        yield _ev("tls",tls)

        # ── 第2轮: AI×5 + IPv6 + DNS 并发 ──
        with ThreadPoolExecutor(7) as ex:
            ai_futs={ex.submit(_ai,s,e):e for e in AI_ENDPOINTS}
            f_v6=ex.submit(_v6,s)
            f_dns=ex.submit(_dns,s)
            for f in as_completed(ai_futs):
                yield _ev("ai",f.result())
            yield _ev("ipv6",f_v6.result())
            yield _ev("dns",f_dns.result())

        # ── done ──
        ai=sorted([f.result() for f in ai_futs],key=lambda r:_AI_ORDER.get(r["name"],99))
        sc,dd,sg=_score(ip,tls,ai,f_v6.result(),f_dns.result())
        it="unknown"
        if ip.get("hosting"): it="datacenter"
        elif ip.get("mobile"): it="mobile"
        elif not ip.get("proxy"): it="residential"
        else: it="datacenter"
        yield _ev("done",{
            "score":sc,"grade":_grade(sc),
            "ip":ip.get("query",""),"country":ip.get("country",""),"city":ip.get("city",""),
            "isp":ip.get("isp",""),"asn":ip.get("as",""),"org":ip.get("org",""),
            "lat":ip.get("lat"),"lon":ip.get("lon"),"ip_type":it,
            "is_proxy":ip.get("proxy",False),"is_hosting":ip.get("hosting",False),
            "is_mobile":ip.get("mobile",False),
            "tls":{"ja3":tls.get("ja3",""),"ja4":tls.get("ja4",""),
                   "http2_fingerprint":tls.get("http2_fingerprint",""),
                   "impersonate_ok":tls.get("_ok",False),"source":tls.get("source","")},
            "ipv6":f_v6.result(),"dns":f_dns.result(),
            "ai_services":ai,"deductions":dd,"suggestions":sg,
        })
    except Exception as e:
        yield _ev("error",{"error":str(e)[:300]})
    finally:
        s.close()


# ── 检查 ──

def _ip(s):
    ok,_,b=_get(s,"http://ip-api.com/json/?fields=status,message,country,city,isp,as,query,proxy,mobile,hosting,lat,lon,org")
    if not ok: return {"error":f"ip-api 不可达: {b[:80]}"}
    try:
        d=json.loads(b)
        if d.get("status")!="success": return {"error":d.get("message","查询失败")}
        return d
    except: return {"error":"解析失败"}

def _tls(s):
    """并行查多个 TLS 检测源，任一成功即返回"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _try_peet():
        ok,_,b=_get(s,"https://tls.peet.ws/api/all",timeout=6)
        if ok:
            d=json.loads(b)
            return {"ja3":d.get("JA3",""),"ja4":d.get("JA4",""),
                    "http2_fingerprint":str(d.get("HTTP2",{}).get("cipher_suites",""))[:80],
                    "source":"tls.peet.ws","error":"","_ok":True}
        raise Exception("peet fail")

    def _try_ja3er():
        ok,_,b=_get(s,"https://ja3er.com/json",timeout=5)
        if ok:
            d=json.loads(b)
            return {"ja3":d.get("ja3",""),"ja4":"","http2_fingerprint":"",
                    "source":"ja3er.com","error":"","_ok":True}
        raise Exception("ja3er fail")

    def _try_httpbin():
        """如果能正常 HTTPS 连通，说明 TLS 握手没被代理破坏"""
        ok,_,_=_get(s,"https://httpbin.org/get",timeout=4)
        if ok:
            return {"ja3":"","ja4":"","http2_fingerprint":"",
                    "source":"https-ok","error":"","_ok":True}
        raise Exception("httpbin fail")

    with ThreadPoolExecutor(3) as ex:
        futs=[ex.submit(fn) for fn in (_try_peet,_try_ja3er,_try_httpbin)]
        for f in as_completed(futs):
            try:
                return f.result()
            except Exception:
                continue

    return {"ja3":"","ja4":"","http2_fingerprint":"","source":"","error":"TLS 检测源均不可达","_ok":False}

def _ai(s,ep):
    t0=time.perf_counter()
    ok,st,b=_get(s,ep["url"],timeout=4)
    ms=int((time.perf_counter()-t0)*1000)
    r={"name":ep["name"],"url":ep["url"],"reachable":ok,"status":st,"latency_ms":ms}
    if not ok: r["error"]=b[:150]
    return r

def _v6(s):
    ok,_,b=_get(s,"https://api64.ipify.org?format=json",timeout=4)
    if not ok: return {"leak":False,"ipv6":None,"note":"无 IPv6 出口"}
    try:
        ip=json.loads(b).get("ip","")
        h=":" in ip
        return {"leak":h,"ipv6":ip if h else None,"note":"检测到 IPv6 出口" if h else "仅 IPv4"}
    except: return {"leak":False,"ipv6":None,"note":"解析失败"}

def _dns(s):
    ok,_,b=_get(s,"https://api.ipify.org?format=text",timeout=4)
    if not ok: return {"leak":False,"note":"DNS 检查失败"}
    return {"leak":False,"exit_ip":b.strip(),"note":"DNS 经代理解析"}


def _score(ip,tls,ai,v6,dns):
    sc=100; dd=[]; sg=[]
    if ip.get("hosting"):
        sc-=20; dd.append({"reason":"IP 为数据中心","points":-20})
        sg.append({"issue":"IP 为数据中心","guide":"机房 IP 容易被风控标记。\n① 更换住宅代理\n② 避免 AWS/GCP/Azure 大厂段"})
    if ip.get("proxy"):
        sc-=15; dd.append({"reason":"IP 被标记为代理","points":-15})
        sg.append({"issue":"IP 被标记为代理","guide":"已被标记为代理/VPN。\n① 换未标记住宅 IP\n② 代理池轮换"})
    if not tls.get("_ok") and not tls.get("error"):
        sc-=15; dd.append({"reason":"TLS 指纹异常","points":-15})
        sg.append({"issue":"TLS 指纹异常","guide":"impersonate 未生效。\n① 切换 HTTP/1.1 ↔ HTTP/2\n② pip install -U curl_cffi\n③ 换 impersonate 目标"})
    if v6.get("leak"):
        sc-=5; dd.append({"reason":"IPv6 泄露","points":-5})
        sg.append({"issue":"IPv6 泄露","guide":"IPv6 出口暴露真实 IP。\n① sysctl disable_ipv6=1\n② 代理配置 IPv6 规则"})
    if dns.get("leak"):
        sc-=10; dd.append({"reason":"DNS 泄露","points":-10})
        sg.append({"issue":"DNS 泄露","guide":"DNS 未走代理。\n① 开启远程 DNS\n② 配置 DoH 走代理"})
    un=[a["name"] for a in ai if not a.get("reachable")]
    for n in un:
        sc-=10; dd.append({"reason":f"{n} 网络不可达","points":-10})
    if un:
        sg.append({"issue":f"不可达: {', '.join(un)}","guide":"端点无法访问。\n① 检查代理规则\n② 切换节点"})
    return max(0,sc),dd,sg
