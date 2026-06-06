import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Divider,
  Input,
  InputNumber,
  Progress,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  Activity,
  CheckCircle2,
  Clock3,
  Eye,
  EyeOff,
  Gauge,
  HardDrive,
  Layers,
  Mail,
  MailPlus,
  MonitorDot,
  PauseCircle,
  PlayCircle,
  Plus,
  RotateCcw,
  Save,
  Server,
  Target,
  Terminal,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
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
] as const;

const PROVIDER_META: Record<string, { icon: string; color: string }> = {
  cloudflare_temp_email: { icon: "☁️", color: "#f97316" },
  cloudflare_local: { icon: "🏠", color: "#f97316" },
  tempmail_lol: { icon: "📬", color: "#8b5cf6" },
  cloudmail_gen: { icon: "📧", color: "#3b82f6" },
  moemail: { icon: "✉️", color: "#06b6d4" },
  inbucket: { icon: "📥", color: "#10b981" },
  duckmail: { icon: "🦆", color: "#84cc16" },
  gptmail: { icon: "🤖", color: "#ec4899" },
  yyds_mail: { icon: "📮", color: "#f59e0b" },
  ddg_mail: { icon: "🔍", color: "#ef4444" },
};

// ── Animated number hook ─────────────────────────────────────────
function useAnimatedNumber(target: number, duration = 600) {
  const [display, setDisplay] = useState(target);
  const prevRef = useRef(target);

  useEffect(() => {
    if (target === prevRef.current) return;
    prevRef.current = target;
    const start = performance.now();
    const from = display;
    const to = target;
    let raf: number;
    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(from + (to - from) * eased));
      if (progress < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  return display;
}

// ── Stat card component ──────────────────────────────────────────
function StatCard({
  label,
  value,
  icon: Icon,
  color,
  suffix = "",
}: {
  label: string;
  value: number | string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  suffix?: string;
}) {
  const numValue = typeof value === "number" ? value : 0;
  const animated = useAnimatedNumber(numValue);
  const display = typeof value === "number" ? animated : value;
  return (
    <motion.div
      className="rk-stat-card"
      whileHover={{ y: -2, boxShadow: `0 4px 20px ${color}22` }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
    >
      <div className="rk-stat-icon" style={{ background: `${color}18`, color }}>
        <Icon className="size-4.5" />
      </div>
      <div className="rk-stat-body">
        <span className="rk-stat-value" style={{ color }}>
          {display}{suffix}
        </span>
        <span className="rk-stat-label">{label}</span>
      </div>
    </motion.div>
  );
}

// ── Field helper ─────────────────────────────────────────────────
function Field({
  label,
  desc,
  children,
  className = "",
}: {
  label: string;
  desc?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`field ${className}`}>
      <label>{label}</label>
      {children}
      {desc && <p>{desc}</p>}
    </div>
  );
}

// ── Log level colors ─────────────────────────────────────────────
const LOG_LEVEL_CONFIG = {
  info: { color: "#94a3b8", bg: "transparent", dot: "#94a3b8" },
  green: { color: "#10b981", bg: "#10b98110", dot: "#10b981" },
  red: { color: "#ef4444", bg: "#ef444410", dot: "#ef4444" },
  yellow: { color: "#f59e0b", bg: "#f59e0b10", dot: "#f59e0b" },
} as const;

// ── Main page ────────────────────────────────────────────────────
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
  const [logFilter, setLogFilter] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Log scroll — logs are reversed (newest at top), so keep scrollTop at 0
  const stickToTop = useCallback(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = 0;
    }
  }, [autoScroll]);

  useEffect(() => {
    stickToTop();
  }, [config?.logs, stickToTop]);

  const handleLogScroll = useCallback(() => {
    const el = logContainerRef.current;
    if (!el) return;
    setAutoScroll(el.scrollTop <= 10);
  }, []);

  // Load
  useEffect(() => {
    if (!didLoad.current) {
      didLoad.current = true;
      load();
      api.getSettings().then((s) => setProxyMode(s.proxy_mode || "single")).catch(() => {});
      api.listProxyNodes({ pool: "register", enabled: true, page_size: 999 })
        .then((d) => setRegisterNodes(d.total)).catch(() => {});
    }
  }, [load]);

  // SSE
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

  // ── Derived values (before early return — hooks rule) ──────────
  const stats: RegisterConfig["stats"] = (config?.stats ?? {}) as RegisterConfig["stats"];
  const providers: MailProvider[] = config?.mail?.providers ?? [];
  const logs: RegisterConfig["logs"] = config?.logs ?? [];
  const successRate = Number(stats.success_rate ?? 0);
  const enabledProviders = providers.filter((p) => p.enable).length;

  const filteredLogs = useMemo(() => {
    if (!logFilter) return [...logs].reverse();
    return [...logs].filter((l) => l.level === logFilter).reverse();
  }, [logs, logFilter]);

  // ── Early returns ────────────────────────────────────────────
  if (loading && !config) {
    return (
      <div className="flex items-center justify-center py-32">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}
          className="size-9 rounded-full border-[3px] border-blue-500/30 border-t-blue-500"
        />
      </div>
    );
  }
  if (!config) return null;

  return (
    <div className="rk-layout">
      {/* ── Left column: Config ─────────────────────────────── */}
      <div className="page-stack">
        {/* Header */}
        <div className="section-head">
          <div>
            <h2 className="section-title">注册配置</h2>
            <p className="section-desc">
              配置会先在前端暂存，点击保存后写入后端；运行中锁定关键参数。
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

        {/* ── Quick settings card ───────────────────────────── */}
        <Card
          className="surface rk-quick-settings"
          title={
            <div className="flex items-center gap-2">
              <Gauge className="size-4 text-blue-500" />
              <span>运行参数</span>
              <Tag color={config.enabled ? "green" : "default"} className="ml-2">{config.enabled ? "运行中" : "待启动"}</Tag>
            </div>
          }
        >
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
            <Field label="线程数">
              <InputNumber
                min={1} max={100}
                value={config.threads}
                disabled={config.enabled}
                onChange={(v) => update({ threads: Math.max(1, Number(v || 1)) })}
                style={{ width: "100%" }}
              />
            </Field>
            {config.mode === "total" ? (
              <Field label="注册总数">
                <InputNumber
                  min={1}
                  value={config.total}
                  disabled={config.enabled}
                  onChange={(v) => update({ total: Math.max(1, Number(v || 1)) })}
                  style={{ width: "100%" }}
                />
              </Field>
            ) : config.mode === "quota" ? (
              <Field label="目标剩余额度">
                <InputNumber
                  min={1}
                  value={config.target_quota}
                  disabled={config.enabled}
                  onChange={(v) => update({ target_quota: Math.max(1, Number(v || 1)) })}
                  style={{ width: "100%" }}
                />
              </Field>
            ) : (
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
            {proxyMode === "pool" ? (
              <Field label="注册代理">
                <Alert
                  type="info"
                  showIcon
                  icon={<Server className="size-4" />}
                  message={`代理池模式已启用，自动使用注册机池节点（可用 ${registerNodes} 个）`}
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
            <Field label="注册密码" desc="留空则随机生成强密码">
              <Input.Password
                value={config.fixed_password || ""}
                disabled={config.enabled}
                onChange={(e) => update({ fixed_password: e.target.value })}
              />
            </Field>
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

          {/* ── 节点淘汰设置 ─────────────────────────────── */}
          <Divider style={{ margin: "12px 0" }} />
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Server className="size-4 text-orange-500" />
              节点自动淘汰
            </div>
            <Switch
              size="small"
              checked={config.auto_disable_failed_nodes ?? true}
              onChange={(v) => update({ auto_disable_failed_nodes: v })}
              disabled={config.enabled}
            />
          </div>
          {config.auto_disable_failed_nodes !== false && (
            <p className="text-xs text-slate-500 mb-3 -mt-1">
              节点连续失败超阈值后自动禁用，防止浪费邮箱和 IP
            </p>
          )}
          <div className="form-grid" style={{ opacity: config.auto_disable_failed_nodes === false ? 0.45 : 1 }}>
            <Field label="OTP 超时淘汰阈值" desc="节点连续收不到验证码的次数上限">
              <InputNumber
                min={1} max={50}
                value={config.max_node_otp_timeouts ?? 5}
                disabled={config.enabled}
                onChange={(v) => update({ max_node_otp_timeouts: Math.max(1, Number(v || 5)) })}
                style={{ width: "100%" }}
              />
            </Field>
            <Field label="Token 失败淘汰阈值" desc="节点连续换不到 token 的次数上限">
              <InputNumber
                min={1} max={50}
                value={config.max_node_token_failures ?? 5}
                disabled={config.enabled}
                onChange={(v) => update({ max_node_token_failures: Math.max(1, Number(v || 5)) })}
                style={{ width: "100%" }}
              />
            </Field>
          </div>
        </Card>

        {/* ── Mail providers card ────────────────────────────── */}
        <Card
          className="surface"
          title={
            <div className="flex items-center gap-2">
              <Mail className="size-4 text-violet-500" />
              <span>邮箱 Provider</span>
            </div>
          }
          extra={
            <Space>
              <Tag color={enabledProviders > 0 ? "green" : "default"}>
                {enabledProviders}/{providers.length} 启用
              </Tag>
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
          {/* Mail global settings */}
          <div className="form-grid rk-mail-globals">
            <Field label="请求超时 (s)">
              <InputNumber
                min={1} size="small"
                value={config.mail.request_timeout}
                disabled={config.enabled}
                onChange={(v) => update({ mail: { ...config.mail, request_timeout: Number(v || 1) } })}
                style={{ width: "100%" }}
              />
            </Field>
            <Field label="验证码等待超时 (s)">
              <InputNumber
                min={1} size="small"
                value={config.mail.wait_timeout}
                disabled={config.enabled}
                onChange={(v) => update({ mail: { ...config.mail, wait_timeout: Number(v || 1) } })}
                style={{ width: "100%" }}
              />
            </Field>
            <Field label="轮询间隔 (s)">
              <InputNumber
                min={0.5} step={0.5} size="small"
                value={config.mail.wait_interval}
                disabled={config.enabled}
                onChange={(v) => update({ mail: { ...config.mail, wait_interval: Number(v || 0.5) } })}
                style={{ width: "100%" }}
              />
            </Field>
          </div>

          <Divider style={{ margin: "14px 0" }} />

          {/* Provider list */}
          {providers.length === 0 ? (
            <div className="rk-empty-state">
              <Mail className="size-10 text-slate-400" />
              <p className="text-slate-500 mt-3 mb-1 font-medium">尚未配置邮箱 Provider</p>
              <p className="text-slate-400 text-sm">点击上方「添加」按钮开始配置邮箱服务</p>
            </div>
          ) : (
            <Collapse
              ghost
              expandIconPosition="end"
              className="rk-provider-list"
              items={providers.map((provider, i) => ({
                key: `${provider.type}-${i}`,
                label: (
                  <ProviderHeader provider={provider} index={i} />
                ),
                extra: (
                  <Space onClick={(e) => e.stopPropagation()}>
                    <Switch
                      size="small"
                      checked={Boolean(provider.enable)}
                      onChange={(v) => {
                        if (!config) return;
                        const next = [...providers];
                        next[i] = { ...next[i], enable: v };
                        update({ mail: { ...config.mail, providers: next } });
                      }}
                      disabled={config.enabled}
                    />
                    {providers.length > 1 && (
                      <Button
                        type="text" size="small" danger
                        icon={<Trash2 className="size-3.5" />}
                        disabled={config.enabled}
                        onClick={() => {
                          if (!config) return;
                          update({ mail: { ...config.mail, providers: providers.filter((_, j) => j !== i) } });
                        }}
                      />
                    )}
                  </Space>
                ),
                children: (
                  <ProviderEditor
                    provider={provider}
                    index={i}
                    providers={providers}
                    disabled={config.enabled}
                  />
                ),
              }))}
            />
          )}
        </Card>
      </div>

      {/* ── Right column: Monitor ────────────────────────────── */}
      <Card
        className="surface"
        title={
          <div className="flex items-center gap-2">
            <MonitorDot className="size-4 text-emerald-500" />
            <span>运行监控</span>
            <Tag color={config.enabled ? "green" : "default"} className="ml-1">{config.enabled ? "实时" : "停止"}</Tag>
          </div>
        }
        styles={{ body: { display: "flex", flexDirection: "column", gap: 14, minHeight: 0, padding: 16 } }}
      >
        {/* Stats grid */}
        <div className="rk-stat-grid">
          <StatCard label="注册成功" value={stats.success || 0} icon={CheckCircle2} color="#10b981" />
          <StatCard label="注册失败" value={stats.fail || 0} icon={XCircle} color="#ef4444" />
          <StatCard label="完成数" value={stats.done || 0} icon={Layers} color="#3b82f6" />
          <StatCard label="运行线程" value={`${stats.running || 0}/${stats.threads || config.threads}`} icon={Activity} color="#8b5cf6" />
          <StatCard label="运行时间" value={stats.elapsed_seconds || 0} icon={Clock3} color="#f59e0b" suffix="s" />
          <StatCard label="平均耗时" value={stats.avg_seconds || 0} icon={Gauge} color="#06b6d4" suffix="s" />
        </div>

        {/* Success rate gauge */}
        <div className="rk-gauge-card">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold">成功率</span>
            <span className="text-sm font-bold font-mono" style={{ color: successRate >= 80 ? "#10b981" : successRate >= 50 ? "#f59e0b" : "#ef4444" }}>
              {successRate}%
            </span>
          </div>
          <Progress
            percent={successRate}
            showInfo={false}
            strokeColor={{
              "0%": "#3b82f6",
              "50%": "#06b6d4",
              "100%": "#10b981",
            }}
            trailColor="var(--line)"
            strokeWidth={8}
          />
          <div className="flex justify-between mt-2 text-xs text-slate-500">
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>

        {/* Pool metrics */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rk-pool-metric">
            <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
              <HardDrive className="size-3.5" />
              <span>当前额度</span>
            </div>
            <span className="text-lg font-bold">{stats.current_quota || 0}</span>
          </div>
          <div className="rk-pool-metric">
            <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
              <Users className="size-3.5" />
              <span>正常账号</span>
            </div>
            <span className="text-lg font-bold">{stats.current_available || 0}</span>
          </div>
        </div>

        {/* Node failure stats (only in pool mode) */}
        {proxyMode === "pool" && (config.node_stats?.length ?? 0) > 0 && (
          <div className="rk-node-stats">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Server className="size-4 text-orange-500" />
                节点失败统计
              </div>
              <Button
                type="text" size="small"
                onClick={async () => {
                  try {
                    await api.resetRegisterNodeStats();
                    message.success("节点统计已重置");
                  } catch {}
                }}
              >
                重置
              </Button>
            </div>
            <div className="rk-node-list">
              {config.node_stats.slice(0, 8).map((ns) => {
                const failRate = ns.total > 0 ? Math.round((ns.otp_timeouts + ns.token_failures) * 100 / ns.total) : 0;
                const isBad = !ns.enabled || failRate >= 50;
                return (
                  <div key={ns.id} className={`rk-node-row ${isBad ? "is-bad" : ""}`}>
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span
                        className={`rk-node-dot ${ns.enabled ? "online" : "offline"}`}
                        title={ns.enabled ? "启用" : "已淘汰"}
                      />
                      <span className="text-xs font-semibold truncate">{ns.name}</span>
                      <span className="text-xs text-slate-400 truncate">{ns.server}:{ns.port}</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs shrink-0">
                      <Tooltip title="OTP 超时">
                        <Tag color={ns.otp_timeouts > 0 ? "orange" : "default"} className="text-xs">{ns.otp_timeouts}</Tag>
                      </Tooltip>
                      <Tooltip title="Token 失败">
                        <Tag color={ns.token_failures > 0 ? "red" : "default"} className="text-xs">{ns.token_failures}</Tag>
                      </Tooltip>
                      <Tooltip title="注册成功">
                        <Tag color={ns.success > 0 ? "green" : "default"} className="text-xs">{ns.success}</Tag>
                      </Tooltip>
                      {ns.last_error && (
                        <Tooltip title={ns.last_error}>
                          <span className="text-red-400 truncate max-w-[80px]">{ns.last_error.slice(0, 20)}</span>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Status alert */}
        <Alert
          message={config.enabled ? "任务运行中，配置项已锁定" : "启动前请确认配置已保存"}
          type={config.enabled ? "success" : "warning"}
          showIcon
          icon={config.enabled ? <PlayCircle className="size-4" /> : undefined}
        />

        {/* Log terminal */}
        <div className="flex flex-col min-h-0 flex-1">
          <div className="rk-log-toolbar">
            <div className="flex items-center gap-2">
              <Terminal className="size-4 text-slate-500" />
              <strong className="text-sm">实时日志</strong>
              <Tag>{filteredLogs.length}</Tag>
            </div>
            <Space size="small">
              {(["info", "green", "yellow", "red"] as const).map((level) => (
                <Tag
                  key={level}
                  color={logFilter === level ? LOG_LEVEL_CONFIG[level].dot : undefined}
                  className="rk-log-filter-tag"
                  style={{
                    cursor: "pointer",
                    opacity: logFilter && logFilter !== level ? 0.4 : 1,
                    color: LOG_LEVEL_CONFIG[level].color,
                  }}
                  onClick={() => setLogFilter(logFilter === level ? null : level)}
                >
                  {level === "info" ? "信息" : level === "green" ? "成功" : level === "yellow" ? "警告" : "错误"}
                </Tag>
              ))}
              <Tooltip title={autoScroll ? "自动滚动中" : "已锁定滚动"}>
                <Button
                  type="text"
                  size="small"
                  icon={autoScroll ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
                  onClick={() => setAutoScroll(!autoScroll)}
                />
              </Tooltip>
            </Space>
          </div>

          <div
            className="log-terminal pipeline-log rk-log-viewer"
            ref={logContainerRef}
            onScroll={handleLogScroll}
          >
            {filteredLogs.length === 0 ? (
              <motion.div
                className="rk-log-empty"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <Terminal className="size-8 text-slate-400 mb-2" />
                <p className="text-slate-500 font-medium">暂无日志</p>
                <p className="text-slate-400 text-xs mt-1">启动任务后这里会显示注册流水</p>
              </motion.div>
            ) : (
              <AnimatePresence mode="popLayout">
                {filteredLogs.map((item, i) => (
                  <motion.div
                    key={`${item.time}-${i}`}
                    className="log-line"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.15 }}
                  >
                    <span className="log-time">{new Date(item.time).toLocaleTimeString()}</span>
                    <span className={`log-${item.level}`}>{item.text}</span>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

// ── Provider header (collapsed state) ─────────────────────────────
function ProviderHeader({ provider, index }: { provider: MailProvider; index: number }) {
  const meta = PROVIDER_META[provider.type] || { icon: "📧", color: "#94a3b8" };
  const domains = Array.isArray(provider.domain) ? provider.domain : [];
  const enabled = Boolean(provider.enable);

  return (
    <div className="flex items-center gap-3 min-w-0">
      <span
        className="rk-provider-dot"
        style={{
          background: enabled ? meta.color : "#94a3b8",
          opacity: enabled ? 1 : 0.4,
        }}
      />
      <span className="text-base">{meta.icon}</span>
      <div className="min-w-0">
        <div className="text-sm font-semibold truncate">
          {provider.type.replace(/_/g, " ")}
          <span className="text-xs text-slate-400 ml-2 font-normal">#{index + 1}</span>
        </div>
        <div className="text-xs text-slate-500 truncate">
          {domains.length > 0 ? `${domains.length} 个域名` : "无域名"}
          {!enabled && <span className="ml-2 text-slate-400">· 已禁用</span>}
        </div>
      </div>
    </div>
  );
}

// ── Provider expanded editor ──────────────────────────────────────
function ProviderEditor({
  provider,
  index,
  providers,
  disabled,
}: {
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
    <div className="rk-provider-editor">
      <div className="form-grid two mb-4">
        <Field label="Provider 类型">
          <Select
            size="small"
            value={t}
            onChange={changeType}
            disabled={disabled}
            options={PROVIDER_TYPES.map((pt) => ({
              value: pt,
              label: `${PROVIDER_META[pt]?.icon || ""} ${pt.replace(/_/g, " ")}`,
            }))}
          />
        </Field>
      </div>

      {/* ── Type-specific fields ─────────────────────────── */}
      {t === "cloudflare_temp_email" && (
        <>
          <div className="form-grid two">
            <Field label="API Base"><Input size="small" value={String(provider.api_base || "")} disabled={disabled} onChange={(e) => update({ api_base: e.target.value })} /></Field>
            <Field label="Admin Auth"><Input size="small" value={String(provider.admin_auth || provider.admin_password || "")} disabled={disabled} onChange={(e) => update({ admin_auth: e.target.value })} /></Field>
            <Field label="Custom Auth"><Input size="small" value={String(provider.custom_auth || "")} disabled={disabled} onChange={(e) => update({ custom_auth: e.target.value })} /></Field>
            <Field label="邮箱前缀"><Input size="small" value={String(provider.email_prefix || "")} disabled={disabled} onChange={(e) => update({ email_prefix: e.target.value })} /></Field>
          </div>
          <div className="rk-switch-row mt-3">
            <Switch size="small" checked={Boolean(provider.enable_random_subdomain)} onChange={(v) => update({ enable_random_subdomain: v })} disabled={disabled} />
            <span>启用随机子域名</span>
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

      {(t === "duckmail" || t === "gptmail") && (
        <div className="mt-3"><Field label="Default Domain"><Input size="small" value={String(provider.default_domain || "")} disabled={disabled} onChange={(e) => update({ default_domain: e.target.value })} /></Field></div>
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

      {t === "inbucket" && (
        <div className="rk-switch-row mt-3">
          <Switch size="small" checked={Boolean(provider.random_subdomain ?? true)} onChange={(v) => update({ random_subdomain: v })} disabled={disabled} />
          <span>启用随机子域名</span>
        </div>
      )}

      {t === "yyds_mail" && (
        <div className="rk-switch-row mt-3">
          <Switch size="small" checked={Boolean(provider.wildcard)} onChange={(v) => update({ wildcard: v })} disabled={disabled} />
          <span>Wildcard 模式</span>
        </div>
      )}
    </div>
  );
}
