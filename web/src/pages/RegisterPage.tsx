import { useEffect, useRef, useCallback } from "react";
import {
  Card, Button, Input, Select, Switch, Tag, Divider, Space, App, Alert,
} from "antd";
import {
  PlayCircleOutlined, PauseCircleOutlined, SaveOutlined,
  ReloadOutlined, PlusOutlined, DeleteOutlined, WarningOutlined,
} from "@ant-design/icons";
import { useRegisterStore } from "../stores/registerStore";
import type { MailProvider, RegisterConfig } from "../types";

const PROVIDER_TYPES = [
  "cloudflare_temp_email", "cloudflare_local", "tempmail_lol",
  "cloudmail_gen", "moemail", "inbucket", "duckmail", "gptmail", "yyds_mail", "ddg_mail",
];

export default function RegisterPage() {
  const { config, loading } = useRegisterStore();
  const load = useRegisterStore((s) => s.load);
  const save = useRegisterStore((s) => s.save);
  const toggle = useRegisterStore((s) => s.toggle);
  const reset = useRegisterStore((s) => s.reset);
  const setFromSSE = useRegisterStore((s) => s.setFromSSE);
  const didLoad = useRef(false);

  useEffect(() => { if (!didLoad.current) { didLoad.current = true; load(); } }, []);

  useEffect(() => {
    let source: EventSource | null = null;
    let closed = false;
    const connect = () => {
      source = new EventSource("/api/register/events");
      source.onmessage = (event) => {
        if (closed) return;
        try { setFromSSE(JSON.parse(event.data) as RegisterConfig); } catch {}
      };
      source.onerror = () => { if (!closed) { source?.close(); setTimeout(connect, 3000); } };
    };
    connect();
    return () => { closed = true; source?.close(); };
  }, []);

  const { message } = App.useApp();
  const handleSave = useCallback(() => save().catch((e) => message.error("保存失败: " + e.message)), [save]);
  const handleToggle = useCallback(() => toggle().catch((e) => message.error("操作失败: " + e.message)), [toggle]);
  const handleReset = useCallback(() => reset().catch((e) => message.error("重置失败: " + e.message)), [reset]);

  if (loading && !config) return <div className="flex justify-center py-20"><div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;
  if (!config) return null;

  const stats = config.stats || {};
  const providers: MailProvider[] = config.mail?.providers || [];
  const logs = config.logs || [];

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 h-[calc(100vh-80px)] min-h-[600px]">
      {/* 左列：配置 */}
      <Card title={<span className="text-base font-semibold">注册配置</span>}
        extra={<Button type="primary" icon={<SaveOutlined />} onClick={handleSave} disabled={config.enabled}>保存配置</Button>}
        className="flex flex-col" styles={{ body: { flex: 1, overflow: "auto" } }}>
        {/* 基本参数 */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Field label="注册模式">
            <Select value={config.mode} onChange={(v) => useRegisterStore.getState().update({ mode: v })} disabled={config.enabled} style={{ width: "100%" }}>
              <Select.Option value="total">注册总数</Select.Option>
              <Select.Option value="quota">号池剩余额度</Select.Option>
              <Select.Option value="available">可用账号数量</Select.Option>
            </Select>
          </Field>
          <Field label="注册总数">
            <Input type="number" value={config.total} onChange={(e) => useRegisterStore.getState().update({ total: Math.max(1, +e.target.value) })}
              disabled={config.enabled || config.mode !== "total"} />
          </Field>
          <Field label="线程数">
            <Input type="number" value={config.threads} onChange={(e) => useRegisterStore.getState().update({ threads: Math.max(1, +e.target.value) })}
              disabled={config.enabled} />
          </Field>
          <Field label="注册代理">
            <Input value={config.proxy} placeholder="http://127.0.0.1:7890" onChange={(e) => useRegisterStore.getState().update({ proxy: e.target.value })}
              disabled={config.enabled} />
          </Field>
          {config.mode === "quota" && <Field label="目标剩余额度">
            <Input type="number" value={config.target_quota} onChange={(e) => useRegisterStore.getState().update({ target_quota: Math.max(1, +e.target.value) })}
              disabled={config.enabled} />
          </Field>}
          {config.mode === "available" && <Field label="目标可用账号">
            <Input type="number" value={config.target_available} onChange={(e) => useRegisterStore.getState().update({ target_available: Math.max(1, +e.target.value) })}
              disabled={config.enabled} />
          </Field>}
          {config.mode !== "total" && <Field label="检查间隔（秒）">
            <Input type="number" value={config.check_interval} onChange={(e) => useRegisterStore.getState().update({ check_interval: Math.max(1, +e.target.value) })}
              disabled={config.enabled} />
          </Field>}
        </div>

        <Divider />

        {/* 邮箱全局设置 */}
        <div className="flex items-center justify-between mb-2">
          <div><strong className="text-sm">邮箱配置</strong><p className="text-xs text-gray-500 mt-0.5">支持 10 种 Provider，按启用顺序轮换</p></div>
          <Button size="small" icon={<PlusOutlined />} disabled={config.enabled} onClick={() => {
            const mail = { ...config.mail, providers: [...providers, { enable: true, type: "cloudflare_temp_email", api_base: "", admin_auth: "", domain: [] }] };
            useRegisterStore.getState().update({ mail });
          }}>添加</Button>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-3">
          <Field label="请求超时"><Input type="number" value={config.mail.request_timeout} disabled={config.enabled}
            onChange={(e) => { const mail = { ...config.mail, request_timeout: +e.target.value }; useRegisterStore.getState().update({ mail }); }} /></Field>
          <Field label="等待验证码超时"><Input type="number" value={config.mail.wait_timeout} disabled={config.enabled}
            onChange={(e) => { const mail = { ...config.mail, wait_timeout: +e.target.value }; useRegisterStore.getState().update({ mail }); }} /></Field>
          <Field label="轮询间隔"><Input type="number" value={config.mail.wait_interval} disabled={config.enabled}
            onChange={(e) => { const mail = { ...config.mail, wait_interval: +e.target.value }; useRegisterStore.getState().update({ mail }); }} /></Field>
        </div>

        {/* Provider 列表 */}
        <div className="space-y-2">
          {providers.map((p, i) => <ProviderEditor key={i} provider={p} index={i} providers={providers} disabled={config.enabled} />)}
        </div>
      </Card>

      {/* 右列：运行结果 */}
      <Card title={<div className="flex items-center gap-2"><span className="text-base font-semibold">运行结果</span>
        <Tag color={config.enabled ? "green" : "default"}>{config.enabled ? "运行中" : "已停止"}</Tag></div>}
        className="flex flex-col" styles={{ body: { flex: 1, display: "flex", flexDirection: "column", minHeight: 0 } }}>
        {/* 统计 */}
        <div className="grid grid-cols-4 gap-2 shrink-0">
          {[
            ["成功/成功率", `${stats.success || 0} / ${stats.success_rate || 0}%`],
            ["失败", stats.fail || 0], ["完成", stats.done || 0],
            ["运行/线程", `${stats.running || 0} / ${stats.threads || config.threads}`],
            ["运行时间", `${stats.elapsed_seconds || 0}s`],
            ["平均注册", `${stats.avg_seconds || 0}s`],
            ["当前额度", stats.current_quota || 0],
            ["正常账号", stats.current_available || 0],
          ].map(([label, val]) => (
            <div key={label as string} className="text-center border rounded-lg p-2">
              <div className="text-[10px] text-gray-500">{label as string}</div>
              <div className="text-sm font-bold mt-0.5">{String(val)}</div>
            </div>
          ))}
        </div>

        {/* 控制 */}
        <div className="flex gap-2 my-3 shrink-0">
          <Button type="primary" block icon={config.enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            onClick={handleToggle}>{config.enabled ? "停止" : "启动"}</Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset} disabled={config.enabled}>重置</Button>
          <Button icon={<SaveOutlined />} onClick={handleSave} disabled={config.enabled}>保存</Button>
        </div>

        <Alert message="启动之前注意先保存配置。" type="warning" showIcon icon={<WarningOutlined />} className="shrink-0 mb-2" />

        {/* 实时日志 */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-2 shrink-0">
            <strong className="text-sm">实时日志</strong>
            <Tag>{logs.length}</Tag>
          </div>
          <div className="flex-1 overflow-y-auto border rounded-lg p-3 bg-gray-50 dark:bg-gray-900 font-mono text-xs leading-6">
            {logs.length === 0 ? <p className="text-gray-400">暂无日志</p> :
              logs.slice().reverse().map((item, i) => (
                <div key={`${item.time}-${i}`}
                  className={item.level === "red" ? "text-red-600" : item.level === "green" ? "text-green-600" : item.level === "yellow" ? "text-orange-600" : "text-gray-600"}>
                  <span className="text-gray-400">{new Date(item.time).toLocaleTimeString()}</span>
                  <span className="pl-2">{item.text}</span>
                </div>
              ))}
          </div>
        </div>
      </Card>
    </div>
  );
}

// ── 辅助 ──────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1"><label className="text-xs text-gray-600">{label}</label>{children}</div>;
}

// ── Provider Editor ───────────────────────────────────────────────────

function ProviderEditor({ provider, index, providers, disabled }: {
  provider: MailProvider; index: number; providers: MailProvider[]; disabled: boolean;
}) {
  const updateStore = useRegisterStore((s) => s.update);
  const update = (upd: Partial<MailProvider>) => {
    const next = [...providers]; next[index] = { ...next[index], ...upd };
    const mail = { ...(useRegisterStore.getState().config?.mail || {}), providers: next };
    updateStore({ mail });
  };
  const remove = () => {
    const next = providers.filter((_, i) => i !== index);
    const mail = { ...(useRegisterStore.getState().config?.mail || {}), providers: next };
    updateStore({ mail });
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
  const subdomains = Array.isArray(provider.subdomain) ? provider.subdomain.join("\n") : "";

  return (
    <Card size="small" title={
      <div className="flex items-center gap-2">
        <Select size="small" value={t} onChange={changeType} disabled={disabled} style={{ width: 200 }}>
          {PROVIDER_TYPES.map(pt => <Select.Option key={pt} value={pt}>{pt}</Select.Option>)}
        </Select>
        <Switch size="small" checked={Boolean(provider.enable)} onChange={(v) => update({ enable: v })} disabled={disabled} />
        <span className="text-xs text-gray-500">启用</span>
        <Button type="text" size="small" danger icon={<DeleteOutlined />}
          disabled={disabled || providers.length <= 1} onClick={remove} className="ml-auto" />
      </div>
    }>
      {/* cloudflare_temp_email */}
      {t === "cloudflare_temp_email" && <>
        <div className="grid grid-cols-2 gap-2">
          <Field label="API Base"><Input size="small" value={String(provider.api_base || "")} disabled={disabled}
            onChange={(e) => update({ api_base: e.target.value })} /></Field>
          <Field label="Admin Auth (x-admin-auth)"><Input size="small" value={String(provider.admin_auth || provider.admin_password || "")} disabled={disabled}
            onChange={(e) => update({ admin_auth: e.target.value })} /></Field>
          <Field label="Custom Auth (x-custom-auth, 可选)"><Input size="small" value={String(provider.custom_auth || "")} disabled={disabled}
            onChange={(e) => update({ custom_auth: e.target.value })} /></Field>
          <Field label="邮箱前缀 (可选)"><Input size="small" value={String(provider.email_prefix || "")} disabled={disabled}
            onChange={(e) => update({ email_prefix: e.target.value })} /></Field>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Switch size="small" checked={Boolean(provider.enable_random_subdomain)}
            onChange={(v) => update({ enable_random_subdomain: v })} disabled={disabled} />
          <span className="text-xs text-gray-500">启用随机子域名 (enableRandomSubdomain)</span>
        </div>
        <div className="mt-2">
          <Field label={`Admin Password (兼容旧版)`}><Input size="small" value={String(provider.admin_password || "")} disabled={disabled}
            onChange={(e) => update({ admin_password: e.target.value })} /></Field>
        </div>
      </>}

      {/* cloudflare_local */}
      {t === "cloudflare_local" && <div className="grid grid-cols-2 gap-2">
        <Field label="API Base (轮询用)"><Input size="small" value={String(provider.api_base || "")} disabled={disabled}
          onChange={(e) => update({ api_base: e.target.value })} /></Field>
        <Field label="邮箱前缀 (可选)"><Input size="small" value={String(provider.email_prefix || "")} disabled={disabled}
          onChange={(e) => update({ email_prefix: e.target.value })} /></Field>
        <Field label="Admin Auth"><Input size="small" value={String(provider.admin_auth || provider.admin_password || "")} disabled={disabled}
          onChange={(e) => update({ admin_auth: e.target.value })} /></Field>
        <Field label="Custom Auth"><Input size="small" value={String(provider.custom_auth || "")} disabled={disabled}
          onChange={(e) => update({ custom_auth: e.target.value })} /></Field>
        <div className="col-span-2">
          <Field label="收件箱 JWT (receive_mailbox_jwt)"><Input size="small" value={String(provider.receive_mailbox_jwt || "")} disabled={disabled}
            onChange={(e) => update({ receive_mailbox_jwt: e.target.value })} /></Field>
        </div>
      </div>}

      {/* 通用: API Base */}
      {["cloudmail_gen", "moemail", "inbucket", "yyds_mail", "ddg_mail"].includes(t) &&
        <Field label="API Base"><Input size="small" value={String(provider.api_base || "")} disabled={disabled}
          onChange={(e) => update({ api_base: e.target.value })} /></Field>}

      {/* 通用: API Key */}
      {["tempmail_lol", "moemail", "duckmail", "gptmail", "yyds_mail"].includes(t) &&
        <Field label="API Key"><Input size="small" value={String(provider.api_key || "")} disabled={disabled}
          onChange={(e) => update({ api_key: e.target.value })} /></Field>}

      {/* cloudmail_gen */}
      {t === "cloudmail_gen" && <div className="grid grid-cols-2 gap-2">
        <Field label="管理员邮箱"><Input size="small" value={String(provider.admin_email || "")} disabled={disabled}
          onChange={(e) => update({ admin_email: e.target.value })} /></Field>
        <Field label="管理员密码"><Input size="small" value={String(provider.admin_password || "")} disabled={disabled}
          onChange={(e) => update({ admin_password: e.target.value })} /></Field>
      </div>}

      {/* ddg_mail */}
      {t === "ddg_mail" && <div className="grid grid-cols-2 gap-2">
        <Field label="DDG Token"><Input size="small" value={String(provider.ddg_token || "")} disabled={disabled}
          onChange={(e) => update({ ddg_token: e.target.value })} /></Field>
        <Field label="CF Inbox JWT"><Input size="small" value={String(provider.cf_inbox_jwt || "")} disabled={disabled}
          onChange={(e) => update({ cf_inbox_jwt: e.target.value })} /></Field>
      </div>}

      {/* 域名 (大部分类型) */}
      {["cloudflare_temp_email", "cloudflare_local", "tempmail_lol", "cloudmail_gen", "moemail", "inbucket", "yyds_mail", "ddg_mail"].includes(t) &&
        <div className="mt-2"><Field label="域名列表 (每行一个)">
          <Input.TextArea size="small" value={domains} disabled={disabled} rows={2}
            onChange={(e) => update({ domain: e.target.value.split(/[\n,]/).map(s => s.trim()).filter(Boolean) })} />
        </Field></div>}

      {/* subdomain */}
      {(t === "cloudmail_gen" || t === "yyds_mail") &&
        <div className="mt-2"><Field label="子域名 (每行一个)">
          <Input.TextArea size="small" value={subdomains} disabled={disabled} rows={2}
            onChange={(e) => update({ subdomain: e.target.value.split(/[\n,]/).map(s => s.trim()).filter(Boolean) })} />
        </Field></div>}

      {/* default_domain */}
      {(t === "duckmail" || t === "gptmail") &&
        <div className="mt-2"><Field label="Default Domain"><Input size="small" value={String(provider.default_domain || "")} disabled={disabled}
          onChange={(e) => update({ default_domain: e.target.value })} /></Field></div>}

      {/* inbucket checkbox */}
      {t === "inbucket" && <div className="mt-2 flex items-center gap-2">
        <Switch size="small" checked={Boolean(provider.random_subdomain ?? true)}
          onChange={(v) => update({ random_subdomain: v })} disabled={disabled} />
        <span className="text-xs text-gray-500">启用随机子域名</span>
      </div>}

      {/* yyds wildcard */}
      {t === "yyds_mail" && <div className="mt-2 flex items-center gap-2">
        <Switch size="small" checked={Boolean(provider.wildcard)}
          onChange={(v) => update({ wildcard: v })} disabled={disabled} />
        <span className="text-xs text-gray-500">Wildcard</span>
      </div>}
    </Card>
  );
}
