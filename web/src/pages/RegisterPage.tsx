import { useEffect, useRef, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Divider,
  Input,
  InputNumber,
  Progress,
  Select,
  Space,
  Switch,
  Tag,
} from "antd";
import {
  Activity,
  Clock3,
  MailPlus,
  PauseCircle,
  PlayCircle,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  Users,
} from "lucide-react";
import { motion } from "framer-motion";
import { useRegisterStore } from "../stores/registerStore";
import { api } from "../api";
import type { MailProvider, RegisterConfig } from "../types";

const PROVIDER_TYPES = [
  "cloudflare_temp_email",
  "cloudflare_local",
  "tempmail_lol",
  "cloudmail_gen",
  "moemail",
  "inbucket",
  "duckmail",
  "gptmail",
  "yyds_mail",
  "ddg_mail",
];

export default function RegisterPage() {
  const { config, loading, saving } = useRegisterStore();
  const load = useRegisterStore((s) => s.load);
  const save = useRegisterStore((s) => s.save);
  const toggle = useRegisterStore((s) => s.toggle);
  const reset = useRegisterStore((s) => s.reset);
  const update = useRegisterStore((s) => s.update);
  const setFromSSE = useRegisterStore((s) => s.setFromSSE);
  const didLoad = useRef(false);
  const { message } = App.useApp();
  const [proxyMode, setProxyMode] = useState("single");
  const [registerNodes, setRegisterNodes] = useState(0);

  useEffect(() => {
    if (!didLoad.current) {
      didLoad.current = true;
      load();
      // 加载代理模式和注册机池节点数
      api.getSettings().then((s) => setProxyMode(s.proxy_mode || "single")).catch(() => {});
      api.listProxyNodes({ pool: "register", enabled: true, page_size: 999 })
        .then((d) => setRegisterNodes(d.total)).catch(() => {});
    }
  }, [load]);

  useEffect(() => {
    let source: EventSource | null = null;
    let closed = false;
    const connect = () => {
      source = new EventSource("/api/register/events");
      source.onmessage = (event) => {
        if (closed) return;
        try {
          setFromSSE(JSON.parse(event.data) as RegisterConfig);
        } catch {}
      };
      source.onerror = () => {
        if (!closed) {
          source?.close();
          window.setTimeout(connect, 3000);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      source?.close();
    };
  }, [setFromSSE]);

  const handleSave = async () => {
    try {
      await save();
      message.success("注册配置已保存");
    } catch (e) {
      message.error("保存失败：" + (e as Error).message);
    }
  };

  const handleToggle = async () => {
    try {
      await toggle();
      message.success(config?.enabled ? "注册任务已停止" : "注册任务已启动");
    } catch (e) {
      message.error("操作失败：" + (e as Error).message);
    }
  };

  const handleReset = async () => {
    try {
      await reset();
      message.success("运行统计已重置");
    } catch (e) {
      message.error("重置失败：" + (e as Error).message);
    }
  };

  if (loading && !config) {
    return <div className="flex justify-center py-20"><div className="animate-spin h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent" /></div>;
  }
  if (!config) return null;

  const stats = config.stats || {};
  const providers: MailProvider[] = config.mail?.providers || [];
  const logs = config.logs || [];
  const successRate = Number(stats.success_rate || 0);

  const runtimeMetrics = [
    { label: "成功", value: stats.success || 0, icon: Users },
    { label: "失败", value: stats.fail || 0, icon: Activity },
    { label: "完成", value: stats.done || 0, icon: MailPlus },
    { label: "运行线程", value: `${stats.running || 0}/${stats.threads || config.threads}`, icon: Activity },
    { label: "运行时间", value: `${stats.elapsed_seconds || 0}s`, icon: Clock3 },
    { label: "平均耗时", value: `${stats.avg_seconds || 0}s`, icon: Clock3 },
    { label: "当前额度", value: stats.current_quota || 0, icon: Activity },
    { label: "正常账号", value: stats.current_available || 0, icon: Users },
  ];

  const enabledProviders = providers.filter((p) => p.enable).length;

  return (
    <div className="register-layout">
      <div className="page-stack">
        <div className="section-head">
          <div>
            <h2 className="section-title">注册配置</h2>
            <p className="section-desc">
              配置会先在前端暂存，点击保存后写入后端；运行中锁定关键参数，避免任务状态漂移。
            </p>
          </div>
          <Space wrap>
            <Button icon={<RotateCcw className="size-4" />} onClick={handleReset} disabled={config.enabled} loading={saving}>
              重置
            </Button>
            <Button icon={<Save className="size-4" />} onClick={handleSave} disabled={config.enabled} loading={saving}>
              保存配置
            </Button>
            <Button
              type="primary"
              danger={config.enabled}
              icon={config.enabled ? <PauseCircle className="size-4" /> : <PlayCircle className="size-4" />}
              onClick={handleToggle}
              loading={saving}
            >
              {config.enabled ? "停止任务" : "启动任务"}
            </Button>
          </Space>
        </div>

        <Card className="surface" title="运行目标" extra={<Tag color={config.enabled ? "green" : "default"}>{config.enabled ? "运行中" : "待启动"}</Tag>}>
          <div className="form-grid">
            <Field label="注册模式">
              <Select
                value={config.mode}
                disabled={config.enabled}
                onChange={(v) => update({ mode: v })}
                options={[
                  { value: "total", label: "注册总数" },
                  { value: "quota", label: "号池剩余额度" },
                  { value: "available", label: "可用账号数量" },
                ]}
              />
            </Field>
            <Field label="注册总数">
              <InputNumber
                min={1}
                value={config.total}
                disabled={config.enabled || config.mode !== "total"}
                onChange={(v) => update({ total: Math.max(1, Number(v || 1)) })}
                style={{ width: "100%" }}
              />
            </Field>
            <Field label="线程数">
              <InputNumber
                min={1}
                max={100}
                value={config.threads}
                disabled={config.enabled}
                onChange={(v) => update({ threads: Math.max(1, Number(v || 1)) })}
                style={{ width: "100%" }}
              />
            </Field>
            {proxyMode === "pool" ? (
              <Field label="注册代理">
                <Alert
                  type="info"
                  showIcon
                  message={`代理池模式已启用，注册机将自动使用注册机池中的节点（可用 ${registerNodes} 个）。`}
                />
              </Field>
            ) : (
              <Field label="注册代理">
                <Input
                  value={config.proxy}
                  placeholder="http://127.0.0.1:7890"
                  disabled={config.enabled}
                  onChange={(e) => update({ proxy: e.target.value })}
                />
              </Field>
            )}
            <Field label="注册密码" desc="注册账号时使用；留空则随机生成。">
              <Input.Password
                value={config.fixed_password || ""}
                disabled={config.enabled}
                onChange={(e) => update({ fixed_password: e.target.value })}
              />
            </Field>
            {config.mode === "quota" && (
              <Field label="目标剩余额度">
                <InputNumber
                  min={1}
                  value={config.target_quota}
                  disabled={config.enabled}
                  onChange={(v) => update({ target_quota: Math.max(1, Number(v || 1)) })}
                  style={{ width: "100%" }}
                />
              </Field>
            )}
            {config.mode === "available" && (
              <Field label="目标可用账号">
                <InputNumber
                  min={1}
                  value={config.target_available}
                  disabled={config.enabled}
                  onChange={(v) => update({ target_available: Math.max(1, Number(v || 1)) })}
                  style={{ width: "100%" }}
                />
              </Field>
            )}
            {config.mode !== "total" && (
              <Field label="检查间隔（秒）">
                <InputNumber
                  min={1}
                  value={config.check_interval}
                  disabled={config.enabled}
                  onChange={(v) => update({ check_interval: Math.max(1, Number(v || 1)) })}
                  style={{ width: "100%" }}
                />
              </Field>
            )}
          </div>
        </Card>

        <Card
          className="surface"
          title="邮箱 Provider"
          extra={
            <Space>
              <Tag>{enabledProviders}/{providers.length} 已启用</Tag>
              <Button
                size="small"
                icon={<Plus className="size-3.5" />}
                disabled={config.enabled}
                onClick={() => {
                  const mail = {
                    ...config.mail,
                    providers: [
                      ...providers,
                      { enable: true, type: "cloudflare_temp_email", api_base: "", admin_auth: "", domain: [] },
                    ],
                  };
                  update({ mail });
                }}
              >
                添加
              </Button>
            </Space>
          }
        >
          <div className="form-grid">
            <Field label="请求超时">
              <InputNumber
                min={1}
                value={config.mail.request_timeout}
                disabled={config.enabled}
                onChange={(v) => update({ mail: { ...config.mail, request_timeout: Number(v || 1) } })}
                style={{ width: "100%" }}
              />
            </Field>
            <Field label="验证码等待超时">
              <InputNumber
                min={1}
                value={config.mail.wait_timeout}
                disabled={config.enabled}
                onChange={(v) => update({ mail: { ...config.mail, wait_timeout: Number(v || 1) } })}
                style={{ width: "100%" }}
              />
            </Field>
            <Field label="轮询间隔">
              <InputNumber
                min={1}
                value={config.mail.wait_interval}
                disabled={config.enabled}
                onChange={(v) => update({ mail: { ...config.mail, wait_interval: Number(v || 1) } })}
                style={{ width: "100%" }}
              />
            </Field>
          </div>

          <Divider />

          <div className="grid gap-3">
            {providers.map((provider, i) => (
              <motion.div
                key={`${provider.type}-${i}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.02 }}
              >
                <ProviderEditor provider={provider} index={i} providers={providers} disabled={config.enabled} />
              </motion.div>
            ))}
          </div>
        </Card>
      </div>

      <Card
        className="surface runtime-panel"
        title={<div className="flex items-center gap-2">运行监控 <Tag color={config.enabled ? "green" : "default"}>{config.enabled ? "实时更新" : "已停止"}</Tag></div>}
        styles={{ body: { display: "flex", flexDirection: "column", gap: 12, minHeight: 0 } }}
      >
        <div className="runtime-metrics">
          {runtimeMetrics.map((item, index) => {
            const Icon = item.icon;
            return (
              <motion.div
                key={item.label}
                className="runtime-mini-card"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.025 }}
              >
                <div className="metric-label"><span>{item.label}</span><Icon className="size-4" /></div>
                <div className="mt-1 text-base font-bold">{String(item.value)}</div>
              </motion.div>
            );
          })}
        </div>

        <div className="surface p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">成功率</span>
            <span className="code-text">{successRate}%</span>
          </div>
          <Progress percent={successRate} status={stats.fail ? "active" : "normal"} strokeColor={{ "0%": "#2563eb", "60%": "#06b6d4", "100%": "#10b981" }} />
        </div>

        <Alert
          message={config.enabled ? "任务运行中，配置项已锁定。" : "启动前请确认配置已保存。"}
          type={config.enabled ? "success" : "warning"}
          showIcon
        />

        <div className="flex min-h-0 flex-col">
          <div className="mb-2 flex items-center justify-between">
            <strong className="text-sm">实时日志</strong>
            <Tag>{logs.length}</Tag>
          </div>
          <div className="log-terminal pipeline-log">
            {logs.length === 0 ? (
              <p className="m-0 text-slate-500">暂无日志，启动任务后这里会显示注册流水。</p>
            ) : (
              logs.slice().reverse().map((item, i) => (
                <div key={`${item.time}-${i}`} className={`log-line log-${item.level}`}>
                  <span className="log-time">{new Date(item.time).toLocaleTimeString()}</span>
                  <span>{item.text}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

function Field({ label, desc, children }: { label: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {desc && <p>{desc}</p>}
    </div>
  );
}

function ProviderEditor({ provider, index, providers, disabled }: {
  provider: MailProvider;
  index: number;
  providers: MailProvider[];
  disabled: boolean;
}) {
  const updateStore = useRegisterStore((s) => s.update);
  const config = useRegisterStore((s) => s.config);

  const update = (upd: Partial<MailProvider>) => {
    if (!config) return;
    const next = [...providers];
    next[index] = { ...next[index], ...upd };
    updateStore({ mail: { ...config.mail, providers: next } });
  };

  const remove = () => {
    if (!config) return;
    const next = providers.filter((_, i) => i !== index);
    updateStore({ mail: { ...config.mail, providers: next } });
  };

  const changeType = (type: string) => {
    const defaults: Record<string, Partial<MailProvider>> = {
      cloudflare_temp_email: { api_base: "", admin_auth: "", custom_auth: "", domain: [], email_prefix: "", enable_random_subdomain: false },
      cloudflare_local: { api_base: "", domain: [], email_prefix: "", admin_auth: "", custom_auth: "", receive_mailbox_jwt: "" },
      tempmail_lol: { api_key: "", domain: [] },
      cloudmail_gen: { api_base: "", admin_email: "", admin_password: "", domain: [], subdomain: [] },
      moemail: { api_base: "", api_key: "", domain: [] },
      inbucket: { api_base: "", domain: [] },
      duckmail: { api_key: "", default_domain: "duckmail.sbs" },
      gptmail: { api_key: "", default_domain: "" },
      yyds_mail: { api_base: "https://maliapi.215.im/v1", api_key: "", domain: [], subdomain: [] },
      ddg_mail: { ddg_token: "", cf_inbox_jwt: "", cf_domain: [], admin_password: "" },
    };
    update({ ...(defaults[type] || {}), type, enable: true });
  };

  const t = provider.type || "cloudflare_temp_email";
  const domains = Array.isArray(provider.domain) ? provider.domain.join("\n") : "";
  const subdomains = Array.isArray(provider.subdomain) ? provider.subdomain.join("\n") : String(provider.subdomain || "");

  return (
    <Card
      size="small"
      title={
        <div className="flex flex-wrap items-center gap-2">
          <Select
            size="small"
            value={t}
            onChange={changeType}
            disabled={disabled}
            style={{ width: 220 }}
            options={PROVIDER_TYPES.map((pt) => ({ value: pt, label: pt }))}
          />
          <Switch size="small" checked={Boolean(provider.enable)} onChange={(v) => update({ enable: v })} disabled={disabled} />
          <span className="text-xs text-slate-500">启用</span>
          <Button
            type="text"
            size="small"
            danger
            icon={<Trash2 className="size-4" />}
            disabled={disabled || providers.length <= 1}
            onClick={remove}
            className="ml-auto"
          />
        </div>
      }
    >
      {t === "cloudflare_temp_email" && (
        <>
          <div className="form-grid two">
            <Field label="API Base"><Input size="small" value={String(provider.api_base || "")} disabled={disabled} onChange={(e) => update({ api_base: e.target.value })} /></Field>
            <Field label="Admin Auth"><Input size="small" value={String(provider.admin_auth || provider.admin_password || "")} disabled={disabled} onChange={(e) => update({ admin_auth: e.target.value })} /></Field>
            <Field label="Custom Auth"><Input size="small" value={String(provider.custom_auth || "")} disabled={disabled} onChange={(e) => update({ custom_auth: e.target.value })} /></Field>
            <Field label="邮箱前缀"><Input size="small" value={String(provider.email_prefix || "")} disabled={disabled} onChange={(e) => update({ email_prefix: e.target.value })} /></Field>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Switch size="small" checked={Boolean(provider.enable_random_subdomain)} onChange={(v) => update({ enable_random_subdomain: v })} disabled={disabled} />
            <span className="text-xs text-slate-500">启用随机子域名</span>
          </div>
          <div className="mt-3">
            <Field label="Admin Password（旧版兼容）"><Input size="small" value={String(provider.admin_password || "")} disabled={disabled} onChange={(e) => update({ admin_password: e.target.value })} /></Field>
          </div>
        </>
      )}

      {t === "cloudflare_local" && (
        <div className="form-grid two">
          <Field label="API Base"><Input size="small" value={String(provider.api_base || "")} disabled={disabled} onChange={(e) => update({ api_base: e.target.value })} /></Field>
          <Field label="邮箱前缀"><Input size="small" value={String(provider.email_prefix || "")} disabled={disabled} onChange={(e) => update({ email_prefix: e.target.value })} /></Field>
          <Field label="Admin Auth"><Input size="small" value={String(provider.admin_auth || provider.admin_password || "")} disabled={disabled} onChange={(e) => update({ admin_auth: e.target.value })} /></Field>
          <Field label="Custom Auth"><Input size="small" value={String(provider.custom_auth || "")} disabled={disabled} onChange={(e) => update({ custom_auth: e.target.value })} /></Field>
          <div className="col-span-2">
            <Field label="收件箱 JWT"><Input size="small" value={String(provider.receive_mailbox_jwt || "")} disabled={disabled} onChange={(e) => update({ receive_mailbox_jwt: e.target.value })} /></Field>
          </div>
        </div>
      )}

      {["cloudmail_gen", "moemail", "inbucket", "yyds_mail", "ddg_mail"].includes(t) && (
        <div className="mt-3"><Field label="API Base"><Input size="small" value={String(provider.api_base || "")} disabled={disabled} onChange={(e) => update({ api_base: e.target.value })} /></Field></div>
      )}

      {["tempmail_lol", "moemail", "duckmail", "gptmail", "yyds_mail"].includes(t) && (
        <div className="mt-3"><Field label="API Key"><Input size="small" value={String(provider.api_key || "")} disabled={disabled} onChange={(e) => update({ api_key: e.target.value })} /></Field></div>
      )}

      {t === "cloudmail_gen" && (
        <div className="form-grid two mt-3">
          <Field label="管理员邮箱"><Input size="small" value={String(provider.admin_email || "")} disabled={disabled} onChange={(e) => update({ admin_email: e.target.value })} /></Field>
          <Field label="管理员密码"><Input size="small" value={String(provider.admin_password || "")} disabled={disabled} onChange={(e) => update({ admin_password: e.target.value })} /></Field>
        </div>
      )}

      {t === "ddg_mail" && (
        <div className="form-grid two mt-3">
          <Field label="DDG Token"><Input size="small" value={String(provider.ddg_token || "")} disabled={disabled} onChange={(e) => update({ ddg_token: e.target.value })} /></Field>
          <Field label="CF Inbox JWT"><Input size="small" value={String(provider.cf_inbox_jwt || "")} disabled={disabled} onChange={(e) => update({ cf_inbox_jwt: e.target.value })} /></Field>
        </div>
      )}

      {["cloudflare_temp_email", "cloudflare_local", "tempmail_lol", "cloudmail_gen", "moemail", "inbucket", "yyds_mail", "ddg_mail"].includes(t) && (
        <div className="mt-3">
          <Field label="域名列表（每行一个）">
            <Input.TextArea size="small" value={domains} disabled={disabled} rows={2} onChange={(e) => update({ domain: e.target.value.split(/[\n,]/).map((s) => s.trim()).filter(Boolean) })} />
          </Field>
        </div>
      )}

      {(t === "cloudmail_gen" || t === "yyds_mail") && (
        <div className="mt-3">
          <Field label="子域名（每行一个）">
            <Input.TextArea size="small" value={subdomains} disabled={disabled} rows={2} onChange={(e) => update({ subdomain: e.target.value.split(/[\n,]/).map((s) => s.trim()).filter(Boolean) })} />
          </Field>
        </div>
      )}

      {(t === "duckmail" || t === "gptmail") && (
        <div className="mt-3"><Field label="Default Domain"><Input size="small" value={String(provider.default_domain || "")} disabled={disabled} onChange={(e) => update({ default_domain: e.target.value })} /></Field></div>
      )}

      {t === "inbucket" && (
        <div className="mt-3 flex items-center gap-2">
          <Switch size="small" checked={Boolean(provider.random_subdomain ?? true)} onChange={(v) => update({ random_subdomain: v })} disabled={disabled} />
          <span className="text-xs text-slate-500">启用随机子域名</span>
        </div>
      )}

      {t === "yyds_mail" && (
        <div className="mt-3 flex items-center gap-2">
          <Switch size="small" checked={Boolean(provider.wildcard)} onChange={(v) => update({ wildcard: v })} disabled={disabled} />
          <span className="text-xs text-slate-500">Wildcard</span>
        </div>
      )}
    </Card>
  );
}
