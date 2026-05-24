import { useEffect, useRef, useCallback } from "react";
import { Card, Input, Select, Switch, InputNumber, Divider } from "antd";
import { useSettingsStore } from "../stores/settingsStore";

function Field({ label, desc, children }: { label: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
      {children}
      {desc && <p className="text-xs text-gray-400">{desc}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const { config, loading } = useSettingsStore();
  const load = useSettingsStore((s) => s.load);
  const save = useSettingsStore((s) => s.save);
  const didLoad = useRef(false);

  useEffect(() => { if (!didLoad.current) { didLoad.current = true; load(); } }, [load]);

  const handleSave = useCallback((updates: Record<string, unknown>) => {
    save(updates).catch((e) => alert("保存失败: " + e.message));
  }, [save]);

  if (loading && !config) return <div className="flex justify-center py-20"><div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;
  if (!config) return null;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">系统设置</h1>
        <p className="text-sm text-gray-500">配置全局参数、Token 保活策略和导出对接</p>
      </div>

      <Card title="基本设置" size="small">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="HTTP 代理" desc="所有上游请求使用的代理地址">
            <Input size="small" defaultValue={String(config.proxy || "")}
              onBlur={(e) => handleSave({ proxy: e.target.value })} />
          </Field>
          <Field label="固定密码（可选）" desc="注册账号时使用的密码，留空则随机生成">
            <Input size="small" defaultValue={String(config.fixed_password || "")}
              onBlur={(e) => handleSave({ fixed_password: e.target.value })} />
          </Field>
          <Field label="OAuth 配置模式">
            <Select size="small" defaultValue={String(config.oauth_profile || "platform")}
              onChange={(v) => handleSave({ oauth_profile: v })} style={{ width: "100%" }}>
              <Select.Option value="platform">Platform (app_2SKx...)</Select.Option>
              <Select.Option value="codex">Codex (app_EMoa...)</Select.Option>
            </Select>
          </Field>
        </div>
      </Card>

      <Card title="Platform OAuth" size="small">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Object.entries(config.oauth || {}).map(([k, v]) => (
            <Field key={k} label={k}>
              <Input size="small" defaultValue={String(v || "")} className="font-mono text-xs"
                onBlur={(e) => handleSave({ oauth: { ...config.oauth, [k]: e.target.value } })} />
            </Field>
          ))}
        </div>
      </Card>

      <Card title="Codex OAuth" size="small">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Object.entries(config.codex_oauth || {}).map(([k, v]) => (
            <Field key={k} label={k}>
              <Input size="small" defaultValue={String(v || "")} className="font-mono text-xs"
                onBlur={(e) => handleSave({ codex_oauth: { ...config.codex_oauth, [k]: e.target.value } })} />
            </Field>
          ))}
        </div>
      </Card>

      <Card title="Token 保活策略" size="small">
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <Field label="启用自动保活" desc="后台自动续期即将过期的 Token">
              <Switch size="small" defaultValue={Boolean(config.token_refresh?.enabled)}
                onChange={(v) => handleSave({ token_refresh: { ...config.token_refresh, enabled: v } })} />
            </Field>
            <Field label="缩减重试" desc="批量操作时仅重试失败的项">
              <Switch size="small" defaultValue={Boolean(config.token_refresh?.retry_failed_only)}
                onChange={(v) => handleSave({ token_refresh: { ...config.token_refresh, retry_failed_only: v } })} />
            </Field>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <Field label="续期间隔（分钟）">
              <InputNumber size="small" defaultValue={config.token_refresh?.interval_minutes || 60} min={1} style={{ width: "100%" }}
                onChange={(v) => v != null && handleSave({ token_refresh: { ...config.token_refresh, interval_minutes: v } })} />
            </Field>
            <Field label="到期阈值（天）" desc="N天内过期的Token会被续期">
              <InputNumber size="small" defaultValue={config.token_refresh?.expiring_days || 5} min={1} style={{ width: "100%" }}
                onChange={(v) => v != null && handleSave({ token_refresh: { ...config.token_refresh, expiring_days: v } })} />
            </Field>
            <Field label="最大并发数" desc="批量刷新并发 (1-50)">
              <InputNumber size="small" defaultValue={config.token_refresh?.max_workers || 10} min={1} max={50} style={{ width: "100%" }}
                onChange={(v) => v != null && handleSave({ token_refresh: { ...config.token_refresh, max_workers: v } })} />
            </Field>
          </div>
        </div>
      </Card>

      <Card title="chatgpt2api 对接" size="small">
        <Field label="导出目录" desc="导出 accounts.json + auth_keys.json 的目标路径">
          <Input size="small" defaultValue={String(config.chatgpt2api?.export_dir || "../chatgpt2api/data")}
            onBlur={(e) => handleSave({ chatgpt2api: { ...config.chatgpt2api, export_dir: e.target.value } })} />
        </Field>
      </Card>

      <Card title="infinite-canvas 对接" size="small">
        <div className="grid grid-cols-3 gap-3">
          <Field label="API 地址">
            <Input size="small" defaultValue={String(config.infinite_canvas?.api_url || "http://127.0.0.1:8080")}
              onBlur={(e) => handleSave({ infinite_canvas: { ...config.infinite_canvas, api_url: e.target.value } })} />
          </Field>
          <Field label="管理员用户名">
            <Input size="small" defaultValue={String(config.infinite_canvas?.admin_username || "admin")}
              onBlur={(e) => handleSave({ infinite_canvas: { ...config.infinite_canvas, admin_username: e.target.value } })} />
          </Field>
          <Field label="管理员密码">
            <Input.Password size="small" defaultValue={String(config.infinite_canvas?.admin_password || "")}
              onBlur={(e) => handleSave({ infinite_canvas: { ...config.infinite_canvas, admin_password: e.target.value } })} />
          </Field>
        </div>
      </Card>
    </div>
  );
}
