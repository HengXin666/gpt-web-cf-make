import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, App, Button, Card, Input, InputNumber, Select, Space, Tag } from "antd";
import { NavLink, Navigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Braces, CheckCircle2, KeyRound, Loader, Network, RefreshCcw, Save, Settings2, ShieldCheck, XCircle } from "lucide-react";
import { api } from "../api";
import { useSettingsStore } from "../stores/settingsStore";
import type { AppConfig, ProxyPurityResult, ProxyTestResult } from "../types";

type Section = "basic" | "oauth" | "refresh" | "proxy";

const sections: Array<{ key: Section; to: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { key: "basic", to: "/settings/basic", label: "基本与代理", icon: Settings2 },
  { key: "oauth", to: "/settings/oauth", label: "OAuth 配置", icon: KeyRound },
  { key: "refresh", to: "/settings/refresh", label: "保活策略", icon: RefreshCcw },
  { key: "proxy", to: "/settings/proxy", label: "反代策略", icon: Network },
];

function Field({ label, desc, children, wide = false }: { label: string; desc?: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={`field settings-field ${wide ? "is-wide" : ""}`}>
      <label>{label}</label>
      {children}
      {desc && <p>{desc}</p>}
    </div>
  );
}

function SettingSwitch({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="settings-switch" role="group">
      <button type="button" className={checked ? "is-active" : ""} onClick={() => onChange(true)}>启用</button>
      <button type="button" className={!checked ? "is-active" : ""} onClick={() => onChange(false)}>关闭</button>
    </div>
  );
}

export default function SettingsPage() {
  const params = useParams();
  const section = params.section as Section;
  const { config, loading } = useSettingsStore();
  const load = useSettingsStore((s) => s.load);
  const save = useSettingsStore((s) => s.save);
  const didLoad = useRef(false);
  const { message } = App.useApp();
  const [draft, setDraft] = useState<AppConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [testingProxy, setTestingProxy] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [proxyResult, setProxyResult] = useState<ProxyTestResult | null>(null);
  type PurityStream = {
    ip?: Record<string, unknown>;
    tls?: Record<string, unknown>;
    ai: Array<Record<string, unknown>>;
    ipv6?: Record<string, unknown>;
    dns?: Record<string, unknown>;
    done?: ProxyPurityResult;
    error?: string;
  };
  const emptyStream: PurityStream = { ai: [] };
  const [purityStream, setPurityStream] = useState<PurityStream | null>(null);
  const [checkingPurity, setCheckingPurity] = useState(false);

  useEffect(() => {
    if (!didLoad.current) {
      didLoad.current = true;
      load();
    }
  }, [load]);

  useEffect(() => {
    if (config) setDraft(config);
  }, [config]);

  const patchDraft = useCallback((updates: Partial<AppConfig>) => {
    setDraft((current) => current ? ({ ...current, ...updates } as AppConfig) : current);
  }, []);

  const saveSection = async (updates: Record<string, unknown>) => {
    setSaving(true);
    try {
      await save(updates);
      message.success("已保存");
    } catch (e) {
      message.error("保存失败：" + (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const fetchUpstreamModels = async () => {
    if (!draft) return;
    setLoadingModels(true);
    try {
      const result = await api.getUpstreamModels(draft.reverse_proxy?.upstream_base_url);
      patchDraft({ reverse_proxy: { ...draft.reverse_proxy, models: result.models } });
      message.success(`已获取 ${result.models.length} 个模型`);
    } catch (e) {
      message.error("获取模型失败：" + (e as Error).message);
    } finally {
      setLoadingModels(false);
    }
  };

  const testProxy = async () => {
    if (!draft) return;
    setTestingProxy(true);
    setProxyResult(null);
    try {
      const result = await api.testProxy(String(draft.proxy || ""));
      setProxyResult(result);
      result.ok ? message.success(`代理可用，延迟 ${result.latency_ms} ms`) : message.error(result.error || `代理不可用，HTTP ${result.status}`);
    } catch (e) {
      message.error("代理测试失败：" + (e as Error).message);
    } finally {
      setTestingProxy(false);
    }
  };

  const checkPurity = async () => {
    if (!draft) return;
    setCheckingPurity(true);
    setPurityStream({ ...emptyStream });
    try {
      for await (const event of api.checkProxyPurityStream(String(draft.proxy || ""))) {
        setPurityStream((prev) => {
          const s = { ...(prev || { ...emptyStream }) };
          if (event.step === "ip") s.ip = event as Record<string, unknown>;
          else if (event.step === "tls") s.tls = event as Record<string, unknown>;
          else if (event.step === "ai") s.ai = [...s.ai, event as Record<string, unknown>];
          else if (event.step === "ipv6") s.ipv6 = event as Record<string, unknown>;
          else if (event.step === "dns") s.dns = event as Record<string, unknown>;
          else if (event.step === "done") s.done = event as unknown as ProxyPurityResult;
          else if (event.step === "error") s.error = (event as Record<string, unknown>).error as string;
          return s;
        });
      }
    } catch (e) {
      setPurityStream({ ...emptyStream, error: (e as Error).message });
    } finally {
      setCheckingPurity(false);
    }
  };

  const currentTitle = useMemo(() => sections.find((item) => item.key === section)?.label || "系统设置", [section]);

  if (!["basic", "oauth", "refresh", "proxy"].includes(section)) {
    return <Navigate to="/settings/basic" replace />;
  }
  if (loading && !draft) {
    return <div className="flex justify-center py-20"><div className="animate-spin h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent" /></div>;
  }
  if (!draft) return null;

  return (
    <div className="settings-layout settings-page">
      <aside className="surface settings-index">
        <div className="settings-index-head">
          <h2>设置</h2>
          <p>按模块保存配置</p>
        </div>
        {sections.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink key={item.key} to={item.to} className={({ isActive }) => isActive ? "is-active" : ""}>
              <Icon className="size-4" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </aside>

      <div className="settings-stack">
        <div className="section-head settings-page-head">
          <div>
            <h2 className="section-title">{currentTitle}</h2>
            <p className="section-desc">改动不会自动写入，点击保存后才会更新后端配置。</p>
          </div>
          <Tag color={saving ? "processing" : "default"}>{saving ? "保存中" : "待编辑"}</Tag>
        </div>

        {section === "basic" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <SettingsCard
              icon={Network}
              title="代理与请求协议"
              actions={
                <>
                  <Button onClick={testProxy} loading={testingProxy}>测试代理延迟</Button>
                  <Button onClick={checkPurity} loading={checkingPurity} icon={<ShieldCheck className="size-4" />}>纯净度检测</Button>
                  <Button type="primary" icon={<Save className="size-4" />} loading={saving} onClick={() => saveSection({ proxy: draft.proxy, oauth_profile: draft.oauth_profile, http: draft.http })}>
                    保存
                  </Button>
                </>
              }
            >
              <div className="settings-form-grid">
                <Field label="HTTP 代理" desc="所有上游请求使用的代理地址；留空表示直连。" wide>
                  <Input value={String(draft.proxy || "")} placeholder="http://127.0.0.1:7890" onChange={(e) => patchDraft({ proxy: e.target.value })} />
                </Field>
                <Field label="请求协议" desc="作用于 curl_cffi 创建的所有 Session。">
                  <Select
                    value={draft.http?.version || "http2"}
                    onChange={(v) => patchDraft({ http: { ...(draft.http || {}), version: v } })}
                    options={[
                      { value: "http2", label: "HTTP/2.0" },
                      { value: "http1.1", label: "强制 HTTP/1.1" },
                    ]}
                  />
                </Field>
                <Field label="OAuth 配置模式">
                  <Select
                    value={String(draft.oauth_profile || "platform")}
                    onChange={(v) => patchDraft({ oauth_profile: v })}
                    options={[
                      { value: "platform", label: "Platform" },
                      { value: "codex", label: "Codex" },
                    ]}
                  />
                </Field>
              </div>
              {proxyResult && (
                <div className="selection-bar mt-4">
                  <strong className="text-sm">{proxyResult.ok ? "代理可用" : "代理不可用"}</strong>
                  <span className="text-sm text-slate-500">延迟 {proxyResult.latency_ms} ms</span>
                  <span className="text-sm text-slate-500">HTTP {proxyResult.status || "-"}</span>
                  <span className="text-sm text-slate-500">协议 {proxyResult.http_version === "http1.1" ? "HTTP/1.1" : "HTTP/2.0"}</span>
                  {proxyResult.error && <span className="text-sm text-red-500">{proxyResult.error}</span>}
                </div>
              )}
              {purityStream && !purityStream.error && <PurityStreamView stream={purityStream} checking={checkingPurity} />}
              {purityStream?.error && (
                <div className="selection-bar mt-4">
                  <span className="text-sm text-red-500">检测失败：{purityStream.error}</span>
                </div>
              )}
            </SettingsCard>
          </motion.div>
        )}

        {section === "oauth" && (
          <motion.div className="settings-stack" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <SettingsCard
              icon={KeyRound}
              title="Platform OAuth"
              actions={<Button type="primary" icon={<Save className="size-4" />} loading={saving} onClick={() => saveSection({ oauth: draft.oauth })}>保存 Platform</Button>}
            >
              <div className="settings-form-grid">
                {Object.entries(draft.oauth || {}).map(([k, v]) => (
                  <Field key={k} label={k}>
                    <Input className="code-text" value={String(v || "")} onChange={(e) => patchDraft({ oauth: { ...draft.oauth, [k]: e.target.value } })} />
                  </Field>
                ))}
              </div>
            </SettingsCard>
            <SettingsCard
              icon={Braces}
              title="Codex OAuth"
              actions={<Tag>暂未支持</Tag>}
            >
              <Alert className="mb-4" type="info" showIcon message="Codex OAuth 暂未支持编辑；当前仅展示内置配置。" />
              <div className="settings-form-grid">
                {Object.entries(draft.codex_oauth || {}).map(([k, v]) => (
                  <Field key={k} label={k}>
                    <Input className="code-text" value={String(v || "")} disabled />
                  </Field>
                ))}
              </div>
            </SettingsCard>
          </motion.div>
        )}

        {section === "refresh" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <SettingsCard
              icon={RefreshCcw}
              title="Token 保活策略"
              actions={<Button type="primary" icon={<Save className="size-4" />} loading={saving} onClick={() => saveSection({ token_refresh: draft.token_refresh })}>保存</Button>}
            >
              <div className="settings-form-grid">
                <Field label="启用自动保活">
                  <SettingSwitch checked={Boolean(draft.token_refresh?.enabled)} onChange={(v) => patchDraft({ token_refresh: { ...draft.token_refresh, enabled: v } })} />
                </Field>
                <Field label="只重试失败项" desc="批量操作后，前端也会保留失败账号用于一键重试。">
                  <SettingSwitch checked={Boolean(draft.token_refresh?.retry_failed_only)} onChange={(v) => patchDraft({ token_refresh: { ...draft.token_refresh, retry_failed_only: v } })} />
                </Field>
                <Field label="续期间隔" desc="单位：分钟。">
                  <InputNumber min={1} addonAfter="分钟" value={draft.token_refresh?.interval_minutes || 60} onChange={(v) => patchDraft({ token_refresh: { ...draft.token_refresh, interval_minutes: Number(v || 1) } })} style={{ width: "100%" }} />
                </Field>
                <Field label="到期阈值" desc="单位：天；N 天内过期的 Token 会被续期。">
                  <InputNumber min={1} addonAfter="天" value={draft.token_refresh?.expiring_days || 5} onChange={(v) => patchDraft({ token_refresh: { ...draft.token_refresh, expiring_days: Number(v || 1) } })} style={{ width: "100%" }} />
                </Field>
                <Field label="最大并发数" desc="单位：个任务；范围 1-50。">
                  <InputNumber min={1} max={50} addonAfter="个" value={draft.token_refresh?.max_workers || 10} onChange={(v) => patchDraft({ token_refresh: { ...draft.token_refresh, max_workers: Number(v || 1) } })} style={{ width: "100%" }} />
                </Field>
              </div>
            </SettingsCard>
          </motion.div>
        )}

        {section === "proxy" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <SettingsCard
              icon={Network}
              title="OpenAI 兼容反代"
              actions={<Button type="primary" icon={<Save className="size-4" />} loading={saving} onClick={() => saveSection({ reverse_proxy: draft.reverse_proxy })}>保存</Button>}
            >
              <div className="settings-form-grid">
                <Field label="启用反代">
                  <SettingSwitch checked={Boolean(draft.reverse_proxy?.enabled)} onChange={(v) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, enabled: v } })} />
                </Field>
                <Field label="负载均衡策略">
                  <Select
                    value={draft.reverse_proxy?.strategy || "round_robin"}
                    onChange={(v) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, strategy: v } })}
                    options={[
                      { value: "round_robin", label: "加权轮询" },
                      { value: "random", label: "随机" },
                    ]}
                  />
                </Field>
                <Field label="上游 Base URL" desc="未内置适配的 OpenAI 兼容接口使用；文本和图片接口会走 ChatGPT Web backend。" wide>
                  <Input value={String(draft.reverse_proxy?.upstream_base_url || "https://api.openai.com")} onChange={(e) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, upstream_base_url: e.target.value } })} />
                </Field>
                <Field label="超时时间">
                  <InputNumber min={5} max={600} addonAfter="秒" value={draft.reverse_proxy?.timeout_seconds || 120} onChange={(v) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, timeout_seconds: Number(v || 120) } })} style={{ width: "100%" }} />
                </Field>
                <Field label="失败重试账号数" desc="遇到 401、429、5xx 时会换账号重试；数量超过账号池时会从头循环。">
                  <InputNumber min={1} max={10} addonAfter="个" value={draft.reverse_proxy?.max_retries || 2} onChange={(v) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, max_retries: Number(v || 1) } })} style={{ width: "100%" }} />
                </Field>
                <Field label="超时后继续轮询" desc="默认关闭；开启后，图片生成轮询超时会视作当前账号失败，并继续尝试下一个可用账号。">
                  <SettingSwitch checked={Boolean(draft.reverse_proxy?.continue_on_timeout)} onChange={(v) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, continue_on_timeout: v } })} />
                </Field>
                <Field label="记忆 API Key" desc="开启后，新建的反代 API Key 会保存明文并可在密钥列表显示；旧密钥无法反推显示。">
                  <SettingSwitch checked={Boolean(draft.reverse_proxy?.remember_keys)} onChange={(v) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, remember_keys: v } })} />
                </Field>
                <Field label="模型列表" desc="可先从上游 /v1/models 获取；也可手动输入后按回车确认，点击标签上的 x 删除。" wide>
                  <Space.Compact className="w-full">
                    <Select
                      mode="tags"
                      className="w-full"
                      open={false}
                      value={draft.reverse_proxy?.models || []}
                      tokenSeparators={[",", " "]}
                      placeholder="输入模型名后按回车，例如 gpt-5.1"
                      onChange={(models) => patchDraft({ reverse_proxy: { ...draft.reverse_proxy, models: models.map((item) => item.trim()).filter(Boolean) } })}
                    />
                    <Button loading={loadingModels} onClick={fetchUpstreamModels}>从上游获取</Button>
                  </Space.Compact>
                </Field>
              </div>
            </SettingsCard>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function PurityStreamView({ stream, checking }: { stream: { ip?: Record<string, unknown>; tls?: Record<string, unknown>; ai: Array<Record<string, unknown>>; ipv6?: Record<string, unknown>; dns?: Record<string, unknown>; done?: ProxyPurityResult; error?: string }; checking: boolean }) {
  const done = stream.done;
  const gradeColors: Record<string, string> = { pure: "#10b981", clean: "#22c55e", moderate: "#f59e0b", risky: "#f97316", dirty: "#ef4444" };
  const gradeLabels: Record<string, string> = { pure: "纯净", clean: "干净", moderate: "一般", risky: "有风险", dirty: "不干净" };
  const ipTypeLabels: Record<string, string> = { residential: "住宅", datacenter: "机房", mobile: "移动网络", unknown: "未知" };
  const pending = <span className="purity-pending"><Loader className="size-3 animate-spin" /> 检测中…</span>;

  return (
    <div className="purity-result mt-4">
      {/* IP 信息 */}
      {stream.ip && !(stream.ip as Record<string, unknown>).error ? (
        <div className="purity-header" style={{ borderLeft: `4px solid ${done ? gradeColors[done.grade] : "#64748b"}` }}>
          {done ? (
            <div className="purity-score" style={{ color: gradeColors[done.grade] }}>
              <span className="purity-score-num">{done.score}</span>
              <span className="purity-score-label">/100</span>
            </div>
          ) : (
            <div className="purity-score" style={{ color: "#64748b" }}>
              <Loader className="size-5 animate-spin" />
            </div>
          )}
          <div className="purity-info">
            {done && <Tag color={gradeColors[done.grade]}>{gradeLabels[done.grade]}</Tag>}
            <span className="text-sm">{String(stream.ip.query || "")} · {String(stream.ip.country || "")} {String(stream.ip.city || "")}</span>
            <span className="text-xs text-slate-500">{String(stream.ip.isp || "")} · {String(stream.ip.as || "")}</span>
          </div>
          <div className="purity-tags">
            {(() => {
              const ipType = done?.ip_type || (stream.ip.hosting ? "datacenter" : stream.ip.mobile ? "mobile" : stream.ip.proxy ? "datacenter" : "residential");
              return <Tag color={ipType === "residential" ? "green" : ipType === "datacenter" ? "orange" : "default"}>{ipTypeLabels[ipType]}</Tag>;
            })()}
            {Boolean(stream.ip.proxy) && <Tag color="orange">标记为代理</Tag>}
            {Boolean(stream.ip.hosting) && <Tag color="orange">机房 IP</Tag>}
          </div>
        </div>
      ) : stream.ip?.error ? (
        <div className="purity-header" style={{ borderLeft: "4px solid #ef4444" }}>
          <XCircle className="size-5 text-red-500" />
          <span className="text-sm text-red-500">{String(stream.ip.error)}</span>
        </div>
      ) : (
        <div className="purity-header">{pending}</div>
      )}

      {/* TLS 指纹 */}
      <div className="purity-section">
        <strong className="text-xs uppercase text-slate-400">TLS 指纹</strong>
        {stream.tls ? (
          <div className="purity-check-row">
            {(() => {
              const tls = stream.tls;
              if (tls.ja3 || tls.ja4) return <CheckCircle2 className="size-4 text-green-500" />;
              if (tls.source === "https-ok") return <CheckCircle2 className="size-4 text-green-500" />;
              if (tls._ok) return <CheckCircle2 className="size-4 text-yellow-500" />;
              return <XCircle className="size-4 text-red-500" />;
            })()}
            <span className="text-sm">
              {(() => {
                const tls = stream.tls;
                if (tls.ja3 || tls.ja4) return `指纹伪装生效${tls.source ? ` (${tls.source})` : ""}`;
                if (tls.source === "https-ok") return "HTTPS 连通正常，指纹检测源不可达";
                if (tls._ok) return "TLS 握手正常";
                return "TLS 异常";
              })()}
            </span>
            {stream.tls.ja4 ? <span className="text-xs text-slate-400 ml-auto">JA4: {String(stream.tls.ja4).slice(0, 32)}</span> : null}
          </div>
        ) : pending}
      </div>

      {/* AI 服务 */}
      <div className="purity-section">
        <strong className="text-xs uppercase text-slate-400">AI 服务可达性</strong>
        {stream.ai.length > 0 ? stream.ai.map((svc) => (
          <div key={String(svc.name)} className="purity-check-row">
            {svc.reachable ? <CheckCircle2 className="size-4 text-green-500" /> : <XCircle className="size-4 text-red-500" />}
            <span className="text-sm">{String(svc.name)}</span>
            <span className="text-xs text-slate-400 ml-auto">
              {svc.reachable ? `${svc.latency_ms}ms · HTTP ${svc.status}` : `不可达 · ${svc.latency_ms}ms`}
            </span>
          </div>
        )) : checking ? pending : <div className="text-xs text-slate-400">未检测</div>}
      </div>

      {/* 泄露检查 */}
      <div className="purity-section">
        <strong className="text-xs uppercase text-slate-400">泄露检查</strong>
        {stream.ipv6 ? (
          <div className="purity-check-row">
            {stream.ipv6.leak ? <XCircle className="size-4 text-red-500" /> : <CheckCircle2 className="size-4 text-green-500" />}
            <span className="text-sm">IPv6: {String(stream.ipv6.note)}</span>
          </div>
        ) : pending}
        {stream.dns ? (
          <div className="purity-check-row">
            {stream.dns.leak ? <XCircle className="size-4 text-red-500" /> : <CheckCircle2 className="size-4 text-green-500" />}
            <span className="text-sm">DNS: {String(stream.dns.note)}</span>
          </div>
        ) : checking && stream.ipv6 ? pending : null}
      </div>

      {/* 扣分 + 修复指南（仅完成时显示） */}
      {done && <>
        {done.deductions.length > 0 && (
          <div className="purity-section">
            <strong className="text-xs uppercase text-slate-400">扣分明细</strong>
            {done.deductions.map((d, i) => (
              <div key={i} className="purity-check-row">
                <span className="text-sm">{d.reason}</span>
                <span className="text-sm text-red-500 ml-auto">{d.points} 分</span>
              </div>
            ))}
          </div>
        )}
        {done.suggestions.length > 0 && (
          <div className="purity-section">
            <strong className="text-xs uppercase text-slate-400">修复指南</strong>
            {done.suggestions.map((s, i) => (
              <div key={i} className="purity-suggestion">
                <div className="purity-suggestion-issue">{s.issue}</div>
                <pre className="purity-suggestion-guide">{s.guide}</pre>
              </div>
            ))}
          </div>
        )}
      </>}
    </div>
  );
}

function SettingsCard({ icon: Icon, title, actions, children }: { icon: React.ComponentType<{ className?: string }>; title: string; actions: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card className="surface settings-card">
      <div className="settings-card-head">
        <div className="settings-card-title">
          <Icon className="size-4" />
          <span>{title}</span>
        </div>
        <div className="settings-card-actions">{actions}</div>
      </div>
      <div className="settings-card-body">{children}</div>
    </Card>
  );
}
