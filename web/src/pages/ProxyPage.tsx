import { useEffect, useRef, useState } from "react";
import { App, Button, Card, Input, Modal, Space, Statistic, Switch, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { BarChart3, Copy, KeyRound, Plus, RefreshCcw, Terminal, Trash2 } from "lucide-react";
import { api } from "../api";
import type { ProxyKey, ProxyLiveLog, ProxyStatus, ProxyUsageAttempt, ProxyUsageEvent, ProxyUsagePoint, ProxyUsageRecord, ProxyUsageSeries, ProxyUsageSummary } from "../types";

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

function formatChartTime(value: string) {
  const date = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function smoothPath(values: number[], width: number, height: number, max: number) {
  if (values.length === 0) return "";
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const points = values.map((value, index) => ({ x: index * step, y: height - (value / Math.max(1, max)) * height }));
  if (points.length === 1) return `M 0 ${points[0].y} L ${width} ${points[0].y}`;
  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x} ${point.y}`;
    const prev = points[index - 1];
    return `${path} C ${prev.x + step * 0.45} ${prev.y}, ${point.x - step * 0.45} ${point.y}, ${point.x} ${point.y}`;
  }, "");
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
        <Card className="surface"><Statistic title="Token 总量" value={usage?.total_tokens || 0} /></Card>
        <Card className="surface"><Statistic title="估算成本" value={formatUsd(usage?.total_cost_usd)} /></Card>
      </div>

      <Card
        className="surface"
        title={<span className="flex items-center gap-2"><BarChart3 className="size-4 text-blue-500" />Token 用量曲线</span>}
      >
        <TokenUsageChart points={series?.points || []} totalCost={series?.total_cost_usd || 0} />
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
        title={<span className="flex items-center gap-2"><BarChart3 className="size-4 text-blue-500" />最近请求</span>}
      >
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
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const width = 860;
  const height = 270;
  const margin = { top: 18, right: 74, bottom: 36, left: 54 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const padded = points.length ? points : [];
  const tokenSeries = padded.map((item) => ({
    input: item.input_tokens + item.image_input_tokens,
    cached: item.cached_input_tokens,
    output: item.output_tokens + item.image_output_tokens,
    total: item.total_tokens,
  }));
  const maxTokens = Math.max(1, ...tokenSeries.flatMap((item) => [item.input, item.cached, item.output, item.total]));
  const maxCost = Math.max(0.000001, ...padded.map((item) => item.cost_usd || 0));
  const inputPath = smoothPath(tokenSeries.map((item) => item.input), plotWidth, plotHeight, maxTokens);
  const cachedPath = smoothPath(tokenSeries.map((item) => item.cached), plotWidth, plotHeight, maxTokens);
  const outputPath = smoothPath(tokenSeries.map((item) => item.output), plotWidth, plotHeight, maxTokens);
  const costPath = smoothPath(padded.map((item) => item.cost_usd || 0), plotWidth, plotHeight, maxCost);
  const latest = padded[padded.length - 1];
  const hover = hoverIndex !== null ? padded[hoverIndex] : null;
  const hoverX = hoverIndex !== null && padded.length > 1 ? (hoverIndex / (padded.length - 1)) * plotWidth : 0;
  const xLabels = padded.length <= 3 ? padded.map((_, index) => index) : [0, Math.floor((padded.length - 1) / 2), padded.length - 1];
  return (
    <div className="usage-chart">
      <div className="usage-chart-head">
        <div className="usage-chart-legend">
          <span><i className="chart-dot input" />输入</span>
          <span><i className="chart-dot cached" />缓存命中</span>
          <span><i className="chart-dot output" />输出</span>
          <span><i className="chart-dot cost" />成本</span>
        </div>
        <div className="usage-chart-meta">
          <span>窗口成本 {formatUsd(totalCost)}</span>
          {padded.some((item) => item.estimated) && <Tag color="gold">含估算</Tag>}
        </div>
      </div>
      {padded.length === 0 ? (
        <div className="usage-chart-empty">暂无用量数据</div>
      ) : (
        <div className="usage-chart-stage">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="usage-chart-svg"
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              const scaleX = width / rect.width;
              const x = (event.clientX - rect.left) * scaleX - margin.left;
              const ratio = Math.max(0, Math.min(1, x / plotWidth));
              setHoverIndex(Math.round(ratio * (padded.length - 1)));
            }}
            onMouseLeave={() => setHoverIndex(null)}
          >
            <g transform={`translate(${margin.left}, ${margin.top})`}>
              {[0, 0.25, 0.5, 0.75, 1].map((line) => (
                <line key={line} x1="0" x2={plotWidth} y1={plotHeight * line} y2={plotHeight * line} className="usage-grid-line" />
              ))}
              <path d={inputPath} className="usage-line input" />
              <path d={cachedPath} className="usage-line cached" />
              <path d={outputPath} className="usage-line output" />
              <path d={costPath} className="usage-line cost" />
              {hover && (
                <>
                  <line x1={hoverX} x2={hoverX} y1="0" y2={plotHeight} className="usage-hover-line" />
                  <circle cx={hoverX} cy={plotHeight - ((hover.cost_usd || 0) / maxCost) * plotHeight} r="4" className="usage-hover-dot cost" />
                </>
              )}
            </g>
            <line x1={margin.left} x2={margin.left} y1={margin.top} y2={margin.top + plotHeight} className="usage-axis-line" />
            <line x1={margin.left + plotWidth} x2={margin.left + plotWidth} y1={margin.top} y2={margin.top + plotHeight} className="usage-axis-line" />
            {[0, 0.5, 1].map((tick) => (
              <g key={`token-${tick}`}>
                <text x={margin.left - 10} y={margin.top + plotHeight - tick * plotHeight + 4} className="usage-axis-text" textAnchor="end">{Math.round(maxTokens * tick)}</text>
                <text x={margin.left + plotWidth + 10} y={margin.top + plotHeight - tick * plotHeight + 4} className="usage-axis-text" textAnchor="start">{formatUsd(maxCost * tick)}</text>
              </g>
            ))}
            {xLabels.map((index) => (
              <text
                key={index}
                x={margin.left + (padded.length > 1 ? (index / (padded.length - 1)) * plotWidth : 0)}
                y={height - 8}
                className="usage-axis-text"
                textAnchor={index === 0 ? "start" : index === padded.length - 1 ? "end" : "middle"}
              >
                {formatChartTime(padded[index].time)}
              </text>
            ))}
            <text x={margin.left} y="12" className="usage-axis-title">tokens</text>
            <text x={width - margin.right} y="12" className="usage-axis-title" textAnchor="end">cost</text>
          </svg>
          {hover && (
            <div className="usage-chart-tooltip" style={{ left: `${((margin.left + hoverX) / width) * 100}%` }}>
              <strong>{formatChartTime(hover.time)}</strong>
              <span>输入 {hover.input_tokens + hover.image_input_tokens}</span>
              <span>缓存 {hover.cached_input_tokens}</span>
              <span>输出 {hover.output_tokens + hover.image_output_tokens}</span>
              <span>成本 {formatUsd(hover.cost_usd)}</span>
              {hover.estimated && <em>含估算</em>}
            </div>
          )}
        </div>
      )}
      {latest && (
        <div className="usage-chart-foot">
          <span>最新：{new Date(latest.time).toLocaleTimeString("zh-CN", { hour12: false })}</span>
          <span>输入 {latest.input_tokens + latest.image_input_tokens}</span>
          <span>缓存 {latest.cached_input_tokens}</span>
          <span>输出 {latest.output_tokens + latest.image_output_tokens}</span>
          <span>成本 {formatUsd(latest.cost_usd)}</span>
        </div>
      )}
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
