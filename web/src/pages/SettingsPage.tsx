import { useCallback, useEffect, useRef, useState } from "react";
import { App, Card, Input, InputNumber, Select, Space, Switch, Tag } from "antd";
import { motion } from "framer-motion";
import { Braces, Cable, KeyRound, RefreshCcw, Settings2, Shield } from "lucide-react";
import { useSettingsStore } from "../stores/settingsStore";

function Field({ label, desc, children }: { label: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {desc && <p>{desc}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const { config, loading } = useSettingsStore();
  const load = useSettingsStore((s) => s.load);
  const save = useSettingsStore((s) => s.save);
  const didLoad = useRef(false);
  const { message } = App.useApp();
  const [savingKey, setSavingKey] = useState("");

  useEffect(() => {
    if (!didLoad.current) {
      didLoad.current = true;
      load();
    }
  }, [load]);

  const handleSave = useCallback(async (key: string, updates: Record<string, unknown>) => {
    setSavingKey(key);
    try {
      await save(updates);
      message.success("设置已保存");
    } catch (e) {
      message.error("保存失败：" + (e as Error).message);
    } finally {
      setSavingKey("");
    }
  }, [message, save]);

  if (loading && !config) {
    return <div className="flex justify-center py-20"><div className="animate-spin h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent" /></div>;
  }
  if (!config) return null;

  const nav = [
    { href: "#basic", label: "基本设置", icon: Settings2 },
    { href: "#oauth", label: "OAuth 配置", icon: KeyRound },
    { href: "#refresh", label: "保活策略", icon: RefreshCcw },
    { href: "#export", label: "导出对接", icon: Cable },
  ];

  return (
    <div className="settings-layout">
      <aside className="surface settings-index">
        <div className="mb-3">
          <h2 className="section-title text-base">策略索引</h2>
          <p className="section-desc">修改后会自动写入后端。</p>
        </div>
        {nav.map((item) => {
          const Icon = item.icon;
          return (
            <a key={item.href} href={item.href}>
              <Icon className="size-4" />
              <span>{item.label}</span>
            </a>
          );
        })}
      </aside>

      <div className="settings-stack">
        <div className="section-head">
          <div>
            <h2 className="section-title">系统设置</h2>
            <p className="section-desc">统一管理代理、OAuth Profile、Token 自动保活和外部系统同步参数。</p>
          </div>
          <Space>
            <Tag color={savingKey ? "processing" : "green"}>{savingKey ? "保存中" : "配置已就绪"}</Tag>
          </Space>
        </div>

        <motion.div id="basic" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="surface" title={<Title icon={Settings2} text="基本设置" />}>
            <div className="form-grid">
              <Field label="HTTP 代理" desc="所有上游请求使用的代理地址">
                <Input
                  defaultValue={String(config.proxy || "")}
                  placeholder="http://127.0.0.1:7890"
                  onBlur={(e) => handleSave("proxy", { proxy: e.target.value })}
                />
              </Field>
              <Field label="固定密码" desc="注册账号时使用；留空则随机生成">
                <Input.Password
                  defaultValue={String(config.fixed_password || "")}
                  onBlur={(e) => handleSave("fixed_password", { fixed_password: e.target.value })}
                />
              </Field>
              <Field label="OAuth 配置模式" desc="决定注册和刷新使用的 OAuth profile">
                <Select
                  defaultValue={String(config.oauth_profile || "platform")}
                  onChange={(v) => handleSave("oauth_profile", { oauth_profile: v })}
                  options={[
                    { value: "platform", label: "Platform" },
                    { value: "codex", label: "Codex" },
                  ]}
                />
              </Field>
            </div>
          </Card>
        </motion.div>

        <motion.div id="oauth" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 }}>
          <Card className="surface" title={<Title icon={KeyRound} text="Platform OAuth" />} extra={<Tag>platform</Tag>}>
            <div className="form-grid two">
              {Object.entries(config.oauth || {}).map(([k, v]) => (
                <Field key={k} label={k}>
                  <Input
                    className="code-text"
                    defaultValue={String(v || "")}
                    onBlur={(e) => handleSave(`oauth.${k}`, { oauth: { ...config.oauth, [k]: e.target.value } })}
                  />
                </Field>
              ))}
            </div>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}>
          <Card className="surface" title={<Title icon={Braces} text="Codex OAuth" />} extra={<Tag>codex</Tag>}>
            <div className="form-grid two">
              {Object.entries(config.codex_oauth || {}).map(([k, v]) => (
                <Field key={k} label={k}>
                  <Input
                    className="code-text"
                    defaultValue={String(v || "")}
                    onBlur={(e) => handleSave(`codex_oauth.${k}`, { codex_oauth: { ...config.codex_oauth, [k]: e.target.value } })}
                  />
                </Field>
              ))}
            </div>
          </Card>
        </motion.div>

        <motion.div id="refresh" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}>
          <Card className="surface" title={<Title icon={RefreshCcw} text="Token 保活策略" />} extra={<Tag color={config.token_refresh?.enabled ? "green" : "default"}>{config.token_refresh?.enabled ? "已启用" : "未启用"}</Tag>}>
            <div className="form-grid">
              <Field label="启用自动保活" desc="后台自动续期即将过期的 Token">
                <Switch
                  defaultValue={Boolean(config.token_refresh?.enabled)}
                  onChange={(v) => handleSave("token_refresh.enabled", { token_refresh: { ...config.token_refresh, enabled: v } })}
                />
              </Field>
              <Field label="缩减重试" desc="批量操作时仅重试失败的项">
                <Switch
                  defaultValue={Boolean(config.token_refresh?.retry_failed_only)}
                  onChange={(v) => handleSave("token_refresh.retry_failed_only", { token_refresh: { ...config.token_refresh, retry_failed_only: v } })}
                />
              </Field>
              <Field label="续期间隔（分钟）">
                <InputNumber
                  min={1}
                  defaultValue={config.token_refresh?.interval_minutes || 60}
                  onChange={(v) => v != null && handleSave("token_refresh.interval_minutes", { token_refresh: { ...config.token_refresh, interval_minutes: v } })}
                  style={{ width: "100%" }}
                />
              </Field>
              <Field label="到期阈值（天）" desc="N 天内过期的 Token 会被续期">
                <InputNumber
                  min={1}
                  defaultValue={config.token_refresh?.expiring_days || 5}
                  onChange={(v) => v != null && handleSave("token_refresh.expiring_days", { token_refresh: { ...config.token_refresh, expiring_days: v } })}
                  style={{ width: "100%" }}
                />
              </Field>
              <Field label="最大并发数" desc="批量刷新并发，建议 1-50">
                <InputNumber
                  min={1}
                  max={50}
                  defaultValue={config.token_refresh?.max_workers || 10}
                  onChange={(v) => v != null && handleSave("token_refresh.max_workers", { token_refresh: { ...config.token_refresh, max_workers: v } })}
                  style={{ width: "100%" }}
                />
              </Field>
            </div>
          </Card>
        </motion.div>

        <motion.div id="export" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }}>
          <Card className="surface" title={<Title icon={Cable} text="导出对接" />}>
            <div className="form-grid">
              <Field label="chatgpt2api 导出目录" desc="导出 accounts.json 与 auth_keys.json 的目标路径">
                <Input
                  defaultValue={String(config.chatgpt2api?.export_dir || "../chatgpt2api/data")}
                  onBlur={(e) => handleSave("chatgpt2api.export_dir", { chatgpt2api: { ...config.chatgpt2api, export_dir: e.target.value } })}
                />
              </Field>
              <Field label="infinite-canvas API 地址">
                <Input
                  defaultValue={String(config.infinite_canvas?.api_url || "http://127.0.0.1:8080")}
                  onBlur={(e) => handleSave("infinite_canvas.api_url", { infinite_canvas: { ...config.infinite_canvas, api_url: e.target.value } })}
                />
              </Field>
              <Field label="管理员用户名">
                <Input
                  defaultValue={String(config.infinite_canvas?.admin_username || "admin")}
                  onBlur={(e) => handleSave("infinite_canvas.admin_username", { infinite_canvas: { ...config.infinite_canvas, admin_username: e.target.value } })}
                />
              </Field>
              <Field label="管理员密码">
                <Input.Password
                  defaultValue={String(config.infinite_canvas?.admin_password || "")}
                  onBlur={(e) => handleSave("infinite_canvas.admin_password", { infinite_canvas: { ...config.infinite_canvas, admin_password: e.target.value } })}
                />
              </Field>
            </div>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}

function Title({ icon: Icon, text }: { icon: React.ComponentType<{ className?: string }>; text: string }) {
  return (
    <span className="flex items-center gap-2">
      <Icon className="size-4 text-blue-500" />
      {text}
    </span>
  );
}
