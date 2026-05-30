import { useEffect, useMemo, useRef, useState } from "react";
import { App, Button, Card, Input, Modal, Space, Statistic, Switch, Table, Tabs, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { BarChart3, Copy, KeyRound, Plus, RefreshCcw, Terminal, Trash2 } from "lucide-react";
import ReactECharts from "echarts-for-react";
import { api } from "../api";
import type { ProxyKey, ProxyLiveLog, ProxyStatus, ProxyUsageAccount, ProxyUsageAttempt, ProxyUsageEvent, ProxyUsagePoint, ProxyUsageRecord, ProxyUsageSeries, ProxyUsageSummary } from "../types";

function formatDate(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function copyText(value: string, done: (text: string) => void) {
  navigator.clipboard?.writeText(value);
  done("已复制");
}

function mergeRecords(current: ProxyUsageRecord[], next: ProxyUsageRecord) {
  const id = next.request_id;
  const filtered = id ? current.filter((item) => item.request_id !== id) : current;
  return [next, ...filtered].slice(0, 120);
}

function applyEvent(current: ProxyUsageSummary | null, event: ProxyUsageEvent): ProxyUsageSummary | null {
  if (!current) return current;
  if (event.type === "snapshot") {
    return { ...current, active: event.active || [], running: event.active?.length || 0 };
  }
  if (!event.record) return current;
  if (event.type === "updated") {
    const active = mergeRecords(current.active || [], event.record);
    return { ...current, active, running: active.length };
  }
  const active = event.type === "started"
    ? mergeRecords(current.active || [], event.record)
    : (current.active || []).filter((item) => item.request_id !== event.record?.request_id);
  const recent = event.type === "completed" ? mergeRecords(current.recent || [], event.record) : current.recent || [];
  return {
    ...current,
    active,
    running: active.length,
    recent,
    total: event.type === "completed" ? current.total + 1 : current.total,
    success: event.type === "completed" && event.record.success ? current.success + 1 : current.success,
    failed: event.type === "completed" && !event.record.success ? current.failed + 1 : current.failed,
    total_cost_usd: event.type === "completed" ? (current.total_cost_usd || 0) + (event.record.cost?.total_cost_usd || 0) : (current.total_cost_usd || 0),
  };
}

function mergeLogs(current: ProxyLiveLog[], next: ProxyLiveLog) {
  return [next, ...current].slice(0, 120);
}

function logClass(level?: string) {
  if (level === "error") return "log-red";
  if (level === "warn") return "log-yellow";
  return "log-green";
}

function formatLatency(value: number, item: ProxyUsageRecord, now: number) {
  if (item.state === "running") {
    const started = Date.parse(item.time || "");
    if (Number.isFinite(started)) {
      return `${Math.max(0, (now - started) / 1000).toFixed(2)} s`;
    }
  }
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${value || 0} ms`;
}

function formatUsd(value?: number) {
  return `$${Number(value || 0).toFixed(6)}`;
}

export default function ProxyPage() {
  const { message } = App.useApp();
  const didLoad = useRef(false);
  const [status, setStatus] = useState<ProxyStatus | null>(null);
  const [keys, setKeys] = useState<ProxyKey[]>([]);
  const [usage, setUsage] = useState<ProxyUsageSummary | null>(null);
  const [series, setSeries] = useState<ProxyUsageSeries | null>(null);
  const [liveLogs, setLiveLogs] = useState<ProxyLiveLog[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [nextStatus, keyResult, nextUsage] = await Promise.all([
        api.getProxyStatus(),
        api.listProxyKeys(),
        api.getProxyUsage(),
      ]);
      setStatus(nextStatus);
      setKeys(keyResult.items);
      setUsage(nextUsage);
      api.getProxyUsageSeries().then(setSeries).catch(() => undefined);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!didLoad.current) {
      didLoad.current = true;
      load();
    }
  }, []);

  useEffect(() => {
    const source = new EventSource("/api/proxy/events");
    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ProxyUsageEvent;
        setUsage((current) => applyEvent(current, data));
        if (data.type === "snapshot") {
          setLiveLogs(data.logs || []);
        } else if (data.type === "log" && data.log) {
          setLiveLogs((current) => mergeLogs(current, data.log as ProxyLiveLog));
        } else if (data.type === "completed") {
          api.getProxyUsage().then(setUsage).catch(() => undefined);
          api.getProxyUsageSeries().then(setSeries).catch(() => undefined);
        }
      } catch {
        // ignore malformed event frames
      }
    };
    return () => source.close();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => api.getProxyUsageSeries().then(setSeries).catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const createKey = async () => {
    const item = await api.createProxyKey(keyName);
    setCreatedKey(item.key);
    setKeyName("");
    await load();
  };

  const toggleKey = async (item: ProxyKey, enabled: boolean) => {
    await api.updateProxyKey(item.id, { enabled });
    message.success(enabled ? "已启用" : "已停用");
    await load();
  };

  const deleteKey = (item: ProxyKey) => {
    Modal.confirm({
      title: `删除密钥 ${item.name}？`,
      content: "删除后使用这个 API Key 的客户端会立即失效。",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        await api.deleteProxyKey(item.id);
        message.success("已删除");
        await load();
      },
    });
  };

  const keyColumns: ColumnsType<ProxyKey> = [
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "API Key",
      dataIndex: "key",
      key: "key",
      render: (value: string | undefined) => value ? (
        <Input.Password
          className="code-text"
          value={value}
          readOnly
          visibilityToggle
          addonAfter={<Button type="text" size="small" onClick={() => copyText(value, message.success)}>复制</Button>}
        />
      ) : <span className="text-slate-400">未记忆</span>,
    },
    { title: "状态", dataIndex: "enabled", key: "enabled", width: 110, render: (enabled: boolean, item) => <Switch checked={enabled} onChange={(v) => toggleKey(item, v)} /> },
    { title: "创建时间", dataIndex: "created_at", key: "created_at", width: 150, render: formatDate },
    { title: "最后使用", dataIndex: "last_used_at", key: "last_used_at", width: 150, render: formatDate },
    {
      title: "操作",
      key: "actions",
      width: 92,
      render: (_, item) => (
        <Tooltip title="删除密钥">
          <Button danger type="text" icon={<Trash2 className="size-4" />} onClick={() => deleteKey(item)} />
        </Tooltip>
      ),
    },
  ];

  const usageColumns: ColumnsType<ProxyUsageRecord> = [
    { title: "时间", dataIndex: "time", key: "time", width: 150, render: formatDate },
    { title: "路径", dataIndex: "path", key: "path", render: (value: string) => <span className="code-text">{value}</span> },
    { title: "模型", dataIndex: "model", key: "model", render: (value: string) => value || "-" },
    { title: "流式", dataIndex: "stream", key: "stream", width: 82, render: (value: boolean, item) => value ? <Tag color="blue">{item.stream_chunks || 0} 块</Tag> : <Tag>否</Tag> },
    { title: "密钥", dataIndex: "api_key", key: "api_key", render: (value: ProxyUsageRecord["api_key"]) => value?.name || "-" },
    {
      title: "状态",
      dataIndex: "status_code",
      key: "status_code",
      width: 94,
      render: (code: number, item) => item.state === "running"
        ? <Tag color="processing">请求中</Tag>
        : <Tag color={item.success ? "green" : "red"}>{code || "ERR"}</Tag>,
    },
    { title: "链路", dataIndex: "attempt_count", key: "attempt_count", width: 90, render: (value: number, item) => `${value || item.attempts?.length || 0} 次` },
    { title: "延迟", dataIndex: "latency_ms", key: "latency_ms", width: 100, render: (value: number, item) => formatLatency(value, item, now) },
    { title: "Tokens", dataIndex: "usage", key: "usage", width: 110, render: (value: ProxyUsageRecord["usage"]) => value?.total_tokens || 0 },
    { title: "成本", dataIndex: "cost", key: "cost", width: 120, render: (value: ProxyUsageRecord["cost"]) => formatUsd(value?.total_cost_usd) },
  ];

  const accountUsageColumns: ColumnsType<ProxyUsageAccount> = [
    { title: "账号", dataIndex: "account_email", key: "account_email", render: (value: string, item) => <div><div className="code-text">{value || "-"}</div><div className="text-xs text-slate-400">{item.account_id || "-"}</div></div> },
    { title: "请求", dataIndex: "requests", key: "requests", width: 90, align: "right" },
    { title: "成功", dataIndex: "success", key: "success", width: 90, align: "right" },
    { title: "失败", dataIndex: "failed", key: "failed", width: 90, align: "right" },
    { title: "输入", dataIndex: "input_tokens", key: "input_tokens", width: 110, align: "right" },
    { title: "缓存", dataIndex: "cached_input_tokens", key: "cached_input_tokens", width: 110, align: "right" },
    { title: "输出", dataIndex: "output_tokens", key: "output_tokens", width: 110, align: "right" },
    { title: "图片", key: "image_tokens", width: 110, align: "right", render: (_, item) => item.image_input_tokens + item.image_output_tokens },
    { title: "总 Tokens", dataIndex: "total_tokens", key: "total_tokens", width: 130, align: "right" },
    { title: "成本", dataIndex: "cost_usd", key: "cost_usd", width: 120, align: "right", render: formatUsd },
    { title: "最后使用", dataIndex: "last_used_at", key: "last_used_at", width: 150, render: formatDate },
  ];

  const dataTabs = [
    {
      key: "trend",
      label: "使用趋势",
      children: <TokenUsageChart points={series?.points || []} totalCost={series?.total_cost_usd || 0} />,
    },
    {
      key: "accounts",
      label: "账户统计",
      children: (
        <Table
          rowKey={(item) => item.account_id || item.account_email}
          columns={accountUsageColumns}
          dataSource={usage?.by_account || []}
          pagination={{ pageSize: 8 }}
          loading={loading}
          scroll={{ x: 1180 }}
        />
      ),
    },
    {
      key: "recent",
      label: "最近请求",
      children: (
        <Table
          rowKey={(item) => item.request_id || `${item.time}-${item.path}-${item.latency_ms}`}
          columns={usageColumns}
          dataSource={[...(usage?.active || []), ...(usage?.recent || [])]}
          pagination={{ pageSize: 12 }}
          loading={loading}
          className="proxy-usage-table"
          expandable={{
            expandedRowRender: (item) => <UsageDetail item={item} />,
            rowExpandable: (item) => Boolean(item.error || item.attempts?.length || item.stream_logs?.length || item.stream),
          }}
        />
      ),
    },
  ];

  return (
    <div className="settings-stack">
      <div className="section-head">
        <div>
          <h2 className="section-title">OpenAI 兼容反代</h2>
          <p className="section-desc">客户端使用这里的 Base URL 和 API Key，请求会由账号池负载均衡转发。</p>
        </div>
        <Button icon={<RefreshCcw className="size-4" />} onClick={load} loading={loading}>刷新</Button>
      </div>

      <div className="stats-grid four">
        <Card className="surface"><Statistic title="可用账号" value={status?.available_accounts || 0} /></Card>
        <Card className="surface"><Statistic title="API Key" value={status?.keys || 0} /></Card>
        <Card className="surface"><Statistic title="请求中" value={usage?.running || 0} /></Card>
        <Card className="surface"><Statistic title="成功请求" value={usage?.success || 0} /></Card>
        <Card className="surface"><Statistic title="超时时间" value={status?.timeout_seconds || 0} suffix="秒" /></Card>
        <Card className="surface"><Statistic title="重试账号" value={status?.max_retries || 0} suffix="个" /></Card>
        <Card className="surface"><Statistic title="Token 总量" value={usage?.total_tokens || 0} /></Card>
        <Card className="surface"><Statistic title="估算成本" value={formatUsd(usage?.total_cost_usd)} /></Card>
      </div>

      <Card className="surface">
        <Tabs
          defaultActiveKey="trend"
          items={dataTabs.map((tab) => ({
            key: tab.key,
            label: tab.key === "trend" ? <span className="flex items-center gap-1"><BarChart3 className="size-4" />{tab.label}</span> : tab.label,
            children: tab.children,
          }))}
        />
      </Card>

      <Card
        className="surface"
        title={<span className="flex items-center gap-2"><Copy className="size-4 text-blue-500" />客户端配置</span>}
      >
        <div className="form-grid two">
          <div className="field">
            <label>Base URL</label>
            <Input value={status?.base_url || ""} readOnly addonAfter={<Button type="text" size="small" onClick={() => copyText(status?.base_url || "", message.success)}>复制</Button>} />
            <p>infinite-canvas 会自动追加 /v1，OpenAI SDK 也可以直接使用 /v1 地址。</p>
          </div>
          <div className="field">
            <label>OpenAI SDK Base URL</label>
            <Input value={status?.v1_base_url || ""} readOnly addonAfter={<Button type="text" size="small" onClick={() => copyText(status?.v1_base_url || "", message.success)}>复制</Button>} />
            <p>上游：{status?.upstream_base_url || "-"}</p>
          </div>
        </div>
      </Card>

      <Card
        className="surface"
        title={<span className="flex items-center gap-2"><KeyRound className="size-4 text-blue-500" />访问密钥</span>}
        extra={<Button type="primary" icon={<Plus className="size-4" />} onClick={() => setCreateOpen(true)}>新建 API Key</Button>}
      >
        <Table rowKey="id" columns={keyColumns} dataSource={keys} pagination={false} loading={loading} />
      </Card>

      <Card
        className="surface"
        title={<span className="flex items-center gap-2"><Terminal className="size-4 text-blue-500" />实时日志</span>}
      >
        <div className="log-terminal proxy-log">
          {liveLogs.length === 0 ? (
            <div className="log-line log-yellow"><span className="log-time">--:--:--</span><span>等待代理请求</span></div>
          ) : liveLogs.map((item) => (
            <div key={`${item.time}-${item.request_id}-${item.message}`} className={`log-line ${logClass(item.level)}`}>
              <span className="log-time">{new Date(item.time).toLocaleTimeString("zh-CN", { hour12: false })}</span>
              <span>{item.request_id ? `[${item.request_id}] ` : ""}{item.message}</span>
            </div>
          ))}
        </div>
      </Card>

      <Modal
        title="新建 API Key"
        open={createOpen}
        okText={createdKey ? "完成" : "创建"}
        cancelText="取消"
        onOk={async () => {
          if (createdKey) {
            setCreatedKey("");
            setCreateOpen(false);
          } else {
            await createKey();
          }
        }}
        onCancel={() => {
          setCreatedKey("");
          setCreateOpen(false);
        }}
      >
        {createdKey ? (
          <Space direction="vertical" className="w-full">
            <Input.Password value={createdKey} readOnly visibilityToggle />
            <Button icon={<Copy className="size-4" />} onClick={() => copyText(createdKey, message.success)}>复制 API Key</Button>
          </Space>
        ) : (
          <Input value={keyName} placeholder="例如 infinite-canvas" onChange={(event) => setKeyName(event.target.value)} />
        )}
      </Modal>
    </div>
  );
}

function TokenUsageChart({ points, totalCost }: { points: ProxyUsagePoint[]; totalCost: number }) {
  const isDark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");

  const option = useMemo(() => {
    const times = points.map((p) => p.time);
    const inputTokens = points.map((p) => p.input_tokens + p.image_input_tokens);
    const cachedTokens = points.map((p) => p.cached_input_tokens);
    const outputTokens = points.map((p) => p.output_tokens + p.image_output_tokens);
    const costUsd = points.map((p) => p.cost_usd || 0);

    const textColor = isDark ? "#94a3b8" : "#64748b";
    const splitLineColor = isDark ? "#1e293b" : "#e2e8f0";

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: isDark ? "#1e293b" : "#fff",
        borderColor: isDark ? "#334155" : "#e2e8f0",
        textStyle: { color: isDark ? "#e2e8f0" : "#1e293b", fontSize: 12 },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter(params: any) {
          if (!params?.length) return "";
          const time = params[0].axisValueLabel;
          const lines = params.map((p: any) => {
            const val = p.seriesName === "成本" ? `$${p.value.toFixed(6)}` : p.value.toLocaleString();
            return `${p.marker} ${p.seriesName}: ${val}`;
          });
          return `<strong>${time}</strong><br/>${lines.join("<br/>")}`;
        },
      },
      legend: {
        data: ["输入", "缓存命中", "输出", "成本"],
        top: 4,
        textStyle: { color: textColor, fontSize: 12 },
      },
      grid: { left: 60, right: 60, top: 40, bottom: 30 },
      xAxis: {
        type: "category",
        data: times,
        axisLabel: {
          color: textColor,
          fontSize: 11,
          formatter(value: string) {
            const d = new Date(value);
            return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
          },
        },
        axisLine: { lineStyle: { color: isDark ? "#334155" : "#cbd5e1" } },
      },
      yAxis: [
        {
          type: "value",
          name: "Tokens",
          position: "left",
          nameTextStyle: { color: textColor },
          axisLabel: { color: textColor, fontSize: 11 },
          splitLine: { lineStyle: { color: splitLineColor } },
        },
        {
          type: "value",
          name: "USD",
          position: "right",
          nameTextStyle: { color: textColor },
          axisLabel: {
            color: textColor,
            fontSize: 11,
            formatter: (v: number) => `$${v.toFixed(4)}`,
          },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "输入",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 4,
          data: inputTokens,
          lineStyle: { width: 2 },
          itemStyle: { color: "#2563eb" },
          areaStyle: { color: "rgba(37,99,235,0.08)" },
        },
        {
          name: "缓存命中",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 4,
          data: cachedTokens,
          lineStyle: { width: 2 },
          itemStyle: { color: "#f59e0b" },
          areaStyle: { color: "rgba(245,158,11,0.08)" },
        },
        {
          name: "输出",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 4,
          data: outputTokens,
          lineStyle: { width: 2 },
          itemStyle: { color: "#10b981" },
          areaStyle: { color: "rgba(16,185,129,0.08)" },
        },
        {
          name: "成本",
          type: "line",
          smooth: true,
          yAxisIndex: 1,
          symbol: "circle",
          symbolSize: 4,
          data: costUsd,
          lineStyle: { width: 2, type: "dashed" },
          itemStyle: { color: "#e11d48" },
        },
      ],
      animation: true,
      animationDuration: 300,
    };
  }, [points, isDark]);

  if (points.length === 0) {
    return <div style={{ textAlign: "center", padding: 48, color: isDark ? "#64748b" : "#94a3b8" }}>暂无用量数据</div>;
  }

  return (
    <div>
      <ReactECharts
        option={option}
        style={{ height: 300, width: "100%" }}
        notMerge
        lazyUpdate
      />
      <div style={{ textAlign: "right", fontSize: 12, color: isDark ? "#64748b" : "#94a3b8", marginTop: 4 }}>
        窗口成本 {formatUsd(totalCost)}
        {points.some((item) => item.estimated) && <Tag color="gold" style={{ marginLeft: 8 }}>含估算</Tag>}
      </div>
    </div>
  );
}

function UsageDetail({ item }: { item: ProxyUsageRecord }) {
  const attempts = item.attempts || [];
  const streamLogs = item.stream_logs || [];
  const cost = item.cost;
  return (
    <div className="usage-detail">
      {cost && (
        <div>
          <strong>Token 与成本</strong>
          <div className="usage-stream-meta">
            <Tag>{cost.pricing_model}</Tag>
            <span>输入 {cost.input_tokens}</span>
            <span>缓存 {cost.cached_input_tokens}</span>
            <span>输出 {cost.output_tokens}</span>
            <span>图像输入 {cost.image_input_tokens}</span>
            <span>图像输出 {cost.image_output_tokens}</span>
            <span>{formatUsd(cost.total_cost_usd)}</span>
            {cost.estimated && <Tag color="gold">估算</Tag>}
          </div>
        </div>
      )}
      {item.stream && (
        <div>
          <strong>流式响应</strong>
          <div className="usage-stream-meta">
            <Tag color="blue">SSE</Tag>
            <span>{item.stream_chunks || streamLogs.length || 0} 块</span>
            <span>{item.response_bytes || 0} bytes</span>
          </div>
          {streamLogs.length > 0 && (
            <pre>{streamLogs.map((log) => `[${new Date(log.time).toLocaleTimeString("zh-CN", { hour12: false })}] ${log.message}`).join("\n")}</pre>
          )}
        </div>
      )}
      {item.error && (
        <div>
          <strong>最终错误</strong>
          <pre>{item.error}</pre>
        </div>
      )}
      {attempts.length > 0 && (
        <div>
          <strong>上游尝试链路</strong>
          <div className="usage-attempts">
            {attempts.map((attempt: ProxyUsageAttempt, index) => (
              <div className="usage-attempt" key={`${index}-${attempt.account?.id || attempt.account?.email || attempt.status_code}`}>
                <div className="usage-attempt-head">
                  <span>#{index + 1}</span>
                  <Tag color={attempt.success ? "green" : (attempt.error === "selected" ? "processing" : "red")}>{attempt.status_code || (attempt.error === "selected" ? "已选择" : "ERR")}</Tag>
                  <span>{attempt.latency_ms} ms</span>
                  <span className="code-text">{attempt.account?.email || "-"}</span>
                </div>
                {attempt.error && attempt.error !== "selected" && <pre>{attempt.error}</pre>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
