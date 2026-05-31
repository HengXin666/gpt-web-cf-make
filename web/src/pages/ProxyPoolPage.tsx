import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App, Button, Empty, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { NodeUsageStat } from "../types";
import { NavLink, Navigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Download,
  Globe,
  Link2,
  Loader,
  Network,
  Play,
  Plus,
  RefreshCcw,
  Search,
  ShieldCheck,
  Trash2,
  Unlink,
  Upload,
  Zap,
} from "lucide-react";
import { api } from "../api";
import { useProxyPoolStore } from "../stores/proxyPoolStore";
import type { ProxyNode, ProxyAssignment } from "../types";

type Section = "nodes" | "assignments";

const sections: Array<{ key: Section; to: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { key: "nodes", to: "/proxy-pool/nodes", label: "节点管理", icon: Globe },
  { key: "assignments", to: "/proxy-pool/assignments", label: "账号分配", icon: Link2 },
];

const protocolColors: Record<string, string> = {
  http: "blue",
  https: "green",
  socks5: "purple",
  ss: "orange",
  vmess: "magenta",
  trojan: "cyan",
  ssr: "default",
};

const nativeProtocols = new Set(["http", "https", "socks5"]);

const gradeColors: Record<string, string> = { pure: "#10b981", clean: "#22c55e", moderate: "#f59e0b", risky: "#f97316", dirty: "#ef4444" };
const gradeLabels: Record<string, string> = { pure: "纯净", clean: "干净", moderate: "一般", risky: "有风险", dirty: "不干净" };

function formatLatency(ms: number): { text: string; color: string } {
  if (ms < 0) return { text: "未测试", color: "#94a3b8" };
  if (ms < 500) return { text: `${ms}ms`, color: "#10b981" };
  if (ms < 1500) return { text: `${ms}ms`, color: "#f59e0b" };
  return { text: `${ms}ms`, color: "#ef4444" };
}

export default function ProxyPoolPage() {
  const params = useParams();
  const section = params.section as Section;
  const store = useProxyPoolStore();
  const { message, notification } = App.useApp();
  const didLoad = useRef(false);

  const [importOpen, setImportOpen] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [importName, setImportName] = useState("");
  const [importType, setImportType] = useState("auto");
  const [importPool, setImportPool] = useState("api");
  const [importing, setImporting] = useState(false);

  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ name: "", protocol: "http", server: "", port: 8080, username: "", password: "" });

  const [search, setSearch] = useState("");
  const [poolFilter, setPoolFilter] = useState("");
  const [protocolFilter, setProtocolFilter] = useState("");
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [testingNode, setTestingNode] = useState<string | null>(null);
  const [purityStream, setPurityStream] = useState<Record<string, unknown> | null>(null);
  const [purityNodeId, setPurityNodeId] = useState<string | null>(null);
  const [sortField, setSortField] = useState(() => localStorage.getItem("proxy-pool-sort-field") || "");
  const [sortOrder, setSortOrder] = useState<"ascend" | "descend" | undefined>(
    () => (localStorage.getItem("proxy-pool-sort-order") as "ascend" | "descend") || undefined
  );

  // Assignments tab
  const [assignSearch, setAssignSearch] = useState("");

  // Auto-refresh
  const [autoRefresh, setAutoRefresh] = useState<{ enabled: boolean; interval_minutes: number; running: boolean; auto_assign_new_accounts?: boolean }>({ enabled: false, interval_minutes: 60, running: false });

  const [nodeUsage, setNodeUsage] = useState<Record<string, NodeUsageStat>>({});

  const loadUsage = () => {
    api.getNodeUsageStats().then((stats) => {
      const map: Record<string, NodeUsageStat> = {};
      stats.forEach((s) => { map[s.proxy_node_id] = s; });
      setNodeUsage(map);
    }).catch(() => {});
  };

  useEffect(() => {
    if (!didLoad.current) {
      didLoad.current = true;
      // 带记忆排序加载
      const savedSortField = localStorage.getItem("proxy-pool-sort-field") || "";
      const savedSortOrder = localStorage.getItem("proxy-pool-sort-order") || "";
      let sort = "";
      if (savedSortField && savedSortOrder) {
        const fieldMap: Record<string, Record<string, string>> = {
          name: { ascend: "name_asc", descend: "name_desc" },
          latency_ms: { ascend: "latency_asc", descend: "latency_desc" },
          score: { ascend: "score_asc", descend: "score_desc" },
          created_at: { ascend: "created_asc", descend: "created_desc" },
        };
        sort = fieldMap[savedSortField]?.[savedSortOrder] || "";
      }
      store.loadNodes({ sort: sort || undefined });
      store.loadSubscriptions();
      store.loadStats();
      store.loadAssignments();
      api.getProxyAutoRefresh().then(setAutoRefresh).catch(() => {});
      loadUsage();
    }
  }, [store]);

  // 每次节点刷新后同步用量
  useEffect(() => {
    if (store.nodes.length > 0) loadUsage();
  }, [store.nodes]);

  const filteredNodes = useMemo(() => {
    let items = store.nodes;
    if (protocolFilter) items = items.filter((n) => n.protocol === protocolFilter);
    if (poolFilter) items = items.filter((n) => n.pool === poolFilter);
    if (search) {
      const s = search.toLowerCase();
      items = items.filter(
        (n) => n.name.toLowerCase().includes(s) || n.server.toLowerCase().includes(s) || n.country.toLowerCase().includes(s)
      );
    }
    return items;
  }, [store.nodes, search, protocolFilter, poolFilter]);

  const filteredAssignments = useMemo(() => {
    if (!assignSearch) return store.assignments;
    const s = assignSearch.toLowerCase();
    return store.assignments.filter((a) => a.email.toLowerCase().includes(s) || a.node_name.toLowerCase().includes(s));
  }, [store.assignments, assignSearch]);

  const handleImport = async () => {
    if (!importUrl.trim()) {
      message.warning("请输入订阅 URL");
      return;
    }
    setImporting(true);
    try {
      const result = await store.importSubscription(importUrl.trim(), importName.trim(), importType, importPool);
      if (result.ok) {
        message.success(`导入成功：解析 ${result.total_parsed} 节点，新增 ${result.added}，更新 ${result.updated}`);
        setImportOpen(false);
        setImportUrl("");
        setImportName("");
      } else {
        message.error(result.error || "导入失败");
      }
    } catch (e) {
      message.error("导入失败：" + (e as Error).message);
    } finally {
      setImporting(false);
    }
  };

  const handleAddNode = async () => {
    if (!addForm.server || !addForm.port) {
      message.warning("请填写服务器和端口");
      return;
    }
    try {
      await store.addNodes([addForm]);
      message.success("节点已添加");
      setAddOpen(false);
      setAddForm({ name: "", protocol: "http", server: "", port: 8080, username: "", password: "" });
    } catch (e) {
      message.error("添加失败：" + (e as Error).message);
    }
  };

  const handleTestNode = useCallback(
    async (id: string) => {
      setTestingNode(id);
      // 清旧结果
      await api.updateProxyNode(id, { latency_ms: -1, score: -1, grade: "", last_error: "" }).catch(() => {});
      await store.loadNodes();
      try {
        const result = await store.testNode(id);
        if (result.ok) {
          message.success(`延迟 ${result.latency_ms}ms`);
        } else {
          message.error(result.error || "测试失败");
        }
      } finally {
        setTestingNode(null);
      }
    },
    [store, message]
  );

  const handlePurityCheck = useCallback(
    async (id: string) => {
      setPurityNodeId(id);
      setPurityStream({ ip: null, tls: null, ai: [], done: null });
      try {
        for await (const event of api.testProxyNodePurity(id)) {
          setPurityStream((prev) => {
            const s = { ...(prev || { ai: [] }) };
            if (event.step === "ip") s.ip = event;
            else if (event.step === "tls") s.tls = event;
            else if (event.step === "ai") s.ai = [...((s.ai as unknown[]) || []), event];
            else if (event.step === "ipv6") s.ipv6 = event;
            else if (event.step === "dns") s.dns = event;
            else if (event.step === "done") s.done = event;
            else if (event.step === "error") s.error = event.error;
            return s;
          });
        }
        await store.loadNodes();
      } catch (e) {
        notification.error({ message: "纯净度检测失败", description: (e as Error).message });
      }
    },
    [store, notification]
  );

  // 并发测试辅助函数 — 测试前清旧结果，每个完成立刻刷新表格
  const runBatch = async (
    ids: string[],
    fn: (id: string) => Promise<unknown>,
    label: string,
  ) => {
    if (ids.length === 0) { message.warning("请先选择节点"); return; }
    const concurrency = 5;
    let done = 0;
    const total = ids.length;
    const msgKey = "batch-" + label;

    // 先清掉旧测试结果
    await Promise.all(ids.map((id) =>
      api.updateProxyNode(id, { latency_ms: -1, score: -1, grade: "", last_error: "", last_tested_at: "" }).catch(() => {})
    ));
    await store.loadNodes();

    const updateMsg = () => message.loading({ content: `${label} ${done}/${total}`, key: msgKey, duration: 0 });
    updateMsg();
    const queue = [...ids];
    const workers = Array.from({ length: Math.min(concurrency, queue.length) }, async () => {
      while (queue.length) {
        const id = queue.shift()!;
        try { await fn(id); } catch { /* skip */ }
        done++;
        updateMsg();
        store.loadNodes();
      }
    });
    await Promise.all(workers);
    message.success({ content: `${label} 完成 ${done}/${total}`, key: msgKey });
    await store.loadNodes();
    await store.loadStats();
  };

  const handleBatchTest = () => runBatch(
    selectedRowKeys,
    (id) => api.testProxyNode(id).then(() => {}),
    "延迟测试",
  );

  const handleDelete = async (ids: string[]) => {
    const result = await store.deleteNodes(ids);
    message.success(`已删除 ${result.removed} 个节点`);
    setSelectedRowKeys([]);
  };

  const handleAssign = async (accountId: string, nodeId: string) => {
    const result = await store.assignNode(accountId, nodeId);
    if (result.ok) {
      message.success("已分配");
    } else {
      message.error(result.error || "分配失败");
    }
  };

  const handleUnassign = async (accountId: string) => {
    await store.unassignNode(accountId);
    message.success("已取消分配");
  };

  // ── 节点表格列 ──────────────────────────────────────────────

  const nodeColumns: ColumnsType<ProxyNode> = [
    {
      title: "名称",
      dataIndex: "name",
      key: "name",
      ellipsis: true,
      sorter: (a, b) => (a.name || a.server).localeCompare(b.name || b.server),
      sortOrder: sortField === "name" ? sortOrder : undefined,
      render: (v: string, r) => (
        <Space direction="vertical" size={0} className="w-full overflow-hidden">
          <span className="font-medium truncate">{v || r.server}</span>
          {r.subscription_id && <Tag className="shrink-0">订阅</Tag>}
        </Space>
      ),
    },
    {
      title: "协议",
      dataIndex: "protocol",
      key: "protocol",
      render: (v: string) => (
        <Tag color={protocolColors[v] || "default"} className="shrink-0">{v}</Tag>
      ),
    },
    {
      title: "池",
      dataIndex: "pool",
      key: "pool",
      render: (v: string) => (
        <Tag color={v === "api" ? "blue" : "green"} className="shrink-0">{v === "api" ? "反代" : "注册机"}</Tag>
      ),
    },
    {
      title: "GPT 请求",
      key: "gpt_usage",
      render: (_, r) => {
        const u = nodeUsage[r.id];
        if (!u) return <span className="text-slate-400">-</span>;
        const last = u.last_request_time ? new Date(u.last_request_time).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";
        return (
          <Tooltip title={`最后: ${last}`}>
            <span className="text-sm whitespace-nowrap">
              <span className="font-medium">{u.total_requests}</span>
              <span className="text-xs text-green-500 ml-1">(+{u.today_requests})</span>
              {u.failed_requests > 0 && <span className="text-xs text-red-500 ml-1">({u.failed_requests}失败)</span>}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: "服务器",
      key: "server",
      ellipsis: true,
      sorter: (a, b) => `${a.server}:${a.port}`.localeCompare(`${b.server}:${b.port}`),
      render: (_, r) => <span className="truncate">{r.server}:{r.port}</span>,
    },
    {
      title: "延迟",
      dataIndex: "latency_ms",
      key: "latency",
      sorter: (a, b) => (a.latency_ms < 0 ? 99999 : a.latency_ms) - (b.latency_ms < 0 ? 99999 : b.latency_ms),
      sortOrder: sortField === "latency_ms" ? sortOrder : undefined,
      render: (v: number) => {
        const { text, color } = formatLatency(v);
        return <span style={{ color }} className="whitespace-nowrap">{text}</span>;
      },
    },
    {
      title: "纯净度",
      key: "purity",
      sorter: (a, b) => (a.score < 0 ? -1 : a.score) - (b.score < 0 ? -1 : b.score),
      sortOrder: sortField === "score" ? sortOrder : undefined,
      render: (_, r) => {
        if (r.score < 0) return <span className="text-slate-400 whitespace-nowrap">未测试</span>;
        return (
          <Space size={4}>
            <Tag color={gradeColors[r.grade] || "#94a3b8"}>{r.score}</Tag>
            <span className="text-xs text-slate-400">{gradeLabels[r.grade]}</span>
          </Space>
        );
      },
    },
    {
      title: "位置",
      key: "location",
      ellipsis: true,
      render: (_, r) => (
        <span className="truncate">{r.country} {r.city} · {r.isp}</span>
      ),
    },
    {
      title: "启用",
      dataIndex: "enabled",
      key: "enabled",
      render: (v: boolean, r) => (
        <Switch size="small" checked={v} onChange={(checked) => store.updateNode(r.id, { enabled: checked })} />
      ),
    },
    {
      title: "操作",
      key: "actions",
      render: (_, r) => (
        <Space size="small">
          <Tooltip title="测试延迟">
            <Button
              size="small"
              type="text"
              icon={<Zap className="size-3.5" />}
              loading={testingNode === r.id || store.testing.has(r.id)}
              onClick={() => handleTestNode(r.id)}
            />
          </Tooltip>
          <Tooltip title="GPT 可达性">
            <Button
              size="small"
              type="text"
              icon={<Network className="size-3.5" />}
              onClick={async () => {
                setTestingNode(r.id);
                try {
                  const result = await api.testProxyNodeGpt(r.id);
                  if (result.ok) {
                    message.success("GPT 可达");
                  } else {
                    message.warning(result.auto_disabled ? "GPT 不可达，已自动禁用" : (result.error || "不可达"));
                  }
                  await store.loadNodes();
                } finally {
                  setTestingNode(null);
                }
              }}
              loading={testingNode === r.id}
            />
          </Tooltip>
          <Tooltip title="纯净度检测">
            <Button
              size="small"
              type="text"
              icon={<ShieldCheck className="size-3.5" />}
              onClick={() => handlePurityCheck(r.id)}
            />
          </Tooltip>
          <Popconfirm title="删除此节点？" onConfirm={() => handleDelete([r.id])}>
            <Button size="small" type="text" danger icon={<Trash2 className="size-3.5" />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // ── 分配表格列 ──────────────────────────────────────────────

  const nodeOptions = useMemo(
    () =>
      store.nodes
        .filter((n) => n.enabled)
        .map((n) => ({
          label: `${n.name || n.server} (${n.protocol}://${n.server}:${n.port})${n.latency_ms >= 0 ? " · " + n.latency_ms + "ms" : ""}`,
          value: n.id,
        })),
    [store.nodes]
  );

  const assignmentColumns: ColumnsType<ProxyAssignment & { usage?: Record<string, unknown> }> = [
    { title: "账号", dataIndex: "email", key: "email", ellipsis: true },
    {
      title: "分配节点",
      key: "node",
      render: (_, r) => (
        <span className="flex items-center gap-1">
          {r.node_name ? (
            <Tag color="blue" className="shrink-0">{r.node_name}</Tag>
          ) : (
            <Tag color="default" className="shrink-0">未分配</Tag>
          )}
          <Select
            style={{ flex: 1, minWidth: 140 }}
            size="small"
            placeholder="更换节点…"
            value={r.proxy_node_id || undefined}
            options={nodeOptions}
            onChange={(v) => handleAssign(r.account_id, v)}
            allowClear
            onClear={() => handleUnassign(r.account_id)}
            showSearch
            filterOption={(input, option) => (option?.label ?? "").toLowerCase().includes(input.toLowerCase())}
          />
        </span>
      ),
    },
    {
      title: "延迟",
      key: "latency",
      sorter: (a, b) => (a.node_latency_ms || 99999) - (b.node_latency_ms || 99999),
      render: (_, r) => {
        const node = store.nodes.find((n) => n.id === r.proxy_node_id);
        if (!node) return <span className="text-slate-400">-</span>;
        const { text, color } = formatLatency(node.latency_ms);
        return <span style={{ color }} className="whitespace-nowrap">{text}</span>;
      },
    },
    {
      title: "Token数",
      key: "tokens",
      sorter: (a, b) => (a.total_tokens || 0) - (b.total_tokens || 0),
      render: (_, r) => <span className="text-sm whitespace-nowrap">{r.total_tokens != null ? Number(r.total_tokens).toLocaleString() : "-"}</span>,
    },
    {
      title: "请求数",
      key: "requests",
      sorter: (a, b) => (a.requests || 0) - (b.requests || 0),
      render: (_, r) => <span className="text-sm whitespace-nowrap">{r.requests != null ? r.requests : "-"}</span>,
    },
    {
      title: "失败率",
      key: "failRate",
      sorter: (a, b) => {
        const ra = a.requests ? (a.failed || 0) / a.requests : 0;
        const rb = b.requests ? (b.failed || 0) / b.requests : 0;
        return ra - rb;
      },
      render: (_, r) => {
        if (!r.requests || r.requests === 0) return <span className="text-slate-400">-</span>;
        const rate = ((r.failed || 0) / r.requests * 100).toFixed(1);
        const color = Number(rate) < 5 ? "#10b981" : Number(rate) < 20 ? "#f59e0b" : "#ef4444";
        return <span style={{ color }} className="whitespace-nowrap">{rate}%</span>;
      },
    },
    {
      title: "操作",
      key: "actions",
      render: (_, r) =>
        r.proxy_node_id ? (
          <Button size="small" type="text" danger icon={<Unlink className="size-3.5" />} onClick={() => handleUnassign(r.account_id)}>
            取消
          </Button>
        ) : null,
    },
  ];

  // ── 已分配数 ────────────────────────────────────────────────

  const assignedCount = store.assignments.filter((a) => a.proxy_node_id).length;

  const currentTitle = useMemo(() => sections.find((item) => item.key === section)?.label || "代理池", [section]);

  if (!["nodes", "assignments"].includes(section)) {
    return <Navigate to="/proxy-pool/nodes" replace />;
  }

  return (
    <div className="settings-layout settings-page">
      <aside className="surface settings-index">
        <div className="settings-index-head">
          <h2>代理池</h2>
          <p>{store.stats ? `${store.stats.total_nodes} 节点 · ${assignedCount} 已分配` : "加载中…"}</p>
        </div>
        {sections.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink key={item.key} to={item.to} className={({ isActive }) => (isActive ? "is-active" : "")}>
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
            <p className="section-desc">
              {section === "nodes" && "导入订阅、管理节点、测试延迟与纯净度。"}
              {section === "assignments" && "为每个账号分配固定代理节点，提升并发与安全性。"}
            </p>
          </div>
        </div>

        {/* ── 节点管理 ─────────────────────────────────────── */}
        {section === "nodes" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            {/* 统计卡片 */}
            {store.stats && (
              <div className="selection-bar mb-4" style={{ flexWrap: "wrap", gap: 12 }}>
                <span className="text-sm">共 <strong>{store.stats.total_nodes}</strong> 节点</span>
                <span className="text-sm">启用 <strong>{store.stats.enabled_nodes}</strong></span>
                <span className="text-sm">已测试 <strong>{store.stats.tested_nodes}</strong></span>
                <span className="text-sm">
                  平均分 <strong style={{ color: store.stats.avg_score >= 70 ? "#10b981" : store.stats.avg_score >= 50 ? "#f59e0b" : "#ef4444" }}>
                    {store.stats.avg_score}
                  </strong>
                </span>
                {store.stats.by_pool && (
                  <>
                    <Tag color="blue">反代 {store.stats.by_pool.api || 0}</Tag>
                    <Tag color="green">注册机 {store.stats.by_pool.register || 0}</Tag>
                  </>
                )}
                <span className="text-sm">已分配 <strong>{store.stats.assigned_accounts}</strong> 账号</span>
              </div>
            )}

            {/* 工具栏 */}
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <Input
                size="small"
                prefix={<Search className="size-3.5 text-slate-400" />}
                placeholder="搜索名称、服务器、国家…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onPressEnter={() => store.loadNodes({ page: 1, search, protocol: protocolFilter, pool: poolFilter })}
                style={{ width: 200 }}
                allowClear
              />
              <Select
                size="small"
                placeholder="协议筛选"
                value={protocolFilter || undefined}
                onChange={(v) => { setProtocolFilter(v || ""); store.loadNodes({ page: 1, protocol: v || "", search, pool: poolFilter }); }}
                options={[
                  { label: "全部协议", value: "" },
                  { label: "HTTP", value: "http" },
                  { label: "HTTPS", value: "https" },
                  { label: "SOCKS5", value: "socks5" },
                  { label: "SS", value: "ss" },
                  { label: "VMess", value: "vmess" },
                  { label: "Trojan", value: "trojan" },
                ]}
                style={{ width: 120 }}
                allowClear
              />
              <Select
                size="small"
                placeholder="池筛选"
                value={poolFilter || undefined}
                onChange={(v) => { setPoolFilter(v || ""); store.loadNodes({ page: 1, pool: v || "", search, protocol: protocolFilter }); }}
                options={[
                  { label: "全部池", value: "" },
                  { label: "反代池", value: "api" },
                  { label: "注册机池", value: "register" },
                ]}
                style={{ width: 100 }}
                allowClear
              />
              <div className="flex-1" />
              <Button size="small" icon={<Upload className="size-3.5" />} onClick={() => setImportOpen(true)}>
                导入订阅
              </Button>
              <Button size="small" icon={<Plus className="size-3.5" />} onClick={() => setAddOpen(true)}>
                手动添加
              </Button>
              <Button size="small" icon={<Play className="size-3.5" />} onClick={handleBatchTest} disabled={selectedRowKeys.length === 0}>
                批量延迟 ({selectedRowKeys.length})
              </Button>
              <Button
                size="small"
                icon={<Network className="size-3.5" />}
                disabled={selectedRowKeys.length === 0}
                onClick={() => runBatch(selectedRowKeys, (id) => api.testProxyNodeGpt(id).then(() => {}), "GPT 检测")}
              >
                GPT 检测
              </Button>
              <Button
                size="small"
                icon={<ShieldCheck className="size-3.5" />}
                disabled={selectedRowKeys.length === 0}
                onClick={() => runBatch(selectedRowKeys, async (id) => {
                  const resp = await fetch(`/api/proxy-pool/nodes/${id}/test-purity`, { method: "POST" });
                  if (!resp.body) return;
                  const reader = resp.body.getReader();
                  const dec = new TextDecoder();
                  let buf = "";
                  while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buf += dec.decode(value, { stream: true });
                    const lines = buf.split("\n");
                    buf = lines.pop() || "";
                  }
                }, "纯净度检测")}
              >
                纯净度
              </Button>
              {selectedRowKeys.length > 0 && (
                <>
                  <Select
                    size="small"
                    placeholder="归类到…"
                    style={{ width: 100 }}
                    onChange={async (pool) => {
                      const result = await store.batchSetPool(selectedRowKeys, pool);
                      message.success(`已归类 ${result.changed} 个节点到${pool === "api" ? "反代池" : "注册机池"}`);
                    }}
                    options={[
                      { label: "→ 反代池", value: "api" },
                      { label: "→ 注册机池", value: "register" },
                    ]}
                  />
                  <Popconfirm title={`删除 ${selectedRowKeys.length} 个节点？`} onConfirm={() => handleDelete(selectedRowKeys)}>
                    <Button size="small" danger icon={<Trash2 className="size-3.5" />}>
                      删除
                    </Button>
                  </Popconfirm>
                </>
              )}
              <Button size="small" icon={<RefreshCcw className="size-3.5" />} onClick={() => store.loadAll()} loading={store.loading}>
                刷新
              </Button>
            </div>

            {/* 订阅管理栏 */}
            {store.subscriptions.length > 0 && (
              <div className="selection-bar mb-4" style={{ flexWrap: "wrap", gap: 12 }}>
                <span className="text-sm">
                  <strong>{store.subscriptions.length}</strong> 个订阅源
                </span>
                <span className="text-xs text-slate-400">
                  {store.subscriptions.map((s) => `${s.name} (${s.node_count})`).join(" · ")}
                </span>
                <div className="flex-1" />
                <Space size="small">
                  <span className="text-xs text-slate-400">自动刷新</span>
                  <Switch
                    size="small"
                    checked={autoRefresh.enabled}
                    onChange={async (v) => {
                      setAutoRefresh((prev) => ({ ...prev, enabled: v }));
                      try {
                        await api.updateProxyAutoRefresh(v, autoRefresh.interval_minutes);
                      } catch {
                        setAutoRefresh((prev) => ({ ...prev, enabled: !v }));
                      }
                    }}
                  />
                  {autoRefresh.enabled && (
                    <Select
                      size="small"
                      value={autoRefresh.interval_minutes}
                      onChange={async (v) => {
                        const result = await api.updateProxyAutoRefresh(true, v);
                        setAutoRefresh(result);
                      }}
                      style={{ width: 100 }}
                      options={[
                        { label: "5 分钟", value: 5 },
                        { label: "15 分钟", value: 15 },
                        { label: "30 分钟", value: 30 },
                        { label: "1 小时", value: 60 },
                        { label: "2 小时", value: 120 },
                        { label: "6 小时", value: 360 },
                      ]}
                    />
                  )}
                  <span className="text-xs text-slate-400 ml-2">注册自动分配</span>
                  <Switch
                    size="small"
                    checked={autoRefresh.auto_assign_new_accounts || false}
                    onChange={async (v) => {
                      // 乐观更新 — 立即切换 UI
                      setAutoRefresh((prev) => ({ ...prev, auto_assign_new_accounts: v }));
                      try {
                        await api.updateProxyAutoRefresh(autoRefresh.enabled, autoRefresh.interval_minutes, v);
                      } catch {
                        // 回滚
                        setAutoRefresh((prev) => ({ ...prev, auto_assign_new_accounts: !v }));
                      }
                    }}
                  />
                  <Button
                    size="small"
                    icon={<Download className="size-3.5" />}
                    onClick={async () => {
                      const result = await store.syncAllSubscriptions();
                      message.success(`同步完成：${result.synced}/${result.total}`);
                    }}
                    loading={store.loading}
                  >
                    全部同步
                  </Button>
                </Space>
              </div>
            )}

            <Table
              size="small"
              rowKey="id"
              columns={nodeColumns}
              dataSource={store.nodes}
              loading={store.loading}
              rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
              pagination={{
                current: store.page,
                pageSize: store.pageSize,
                total: store.total,
                showSizeChanger: true,
                showTotal: (t) => `共 ${t} 个节点`,
                pageSizeOptions: ["20", "50", "100", "200"],
              }}
              onChange={(pag, _filters, sorter) => {
                // 排序映射
                let sort = "";
                if (sorter && !Array.isArray(sorter) && sorter.field && sorter.order) {
                  const fieldMap: Record<string, Record<string, string>> = {
                    name: { ascend: "name_asc", descend: "name_desc" },
                    latency_ms: { ascend: "latency_asc", descend: "latency_desc" },
                    score: { ascend: "score_asc", descend: "score_desc" },
                    created_at: { ascend: "created_asc", descend: "created_desc" },
                  };
                  const key = String(sorter.field);
                  const order = sorter.order;
                  sort = fieldMap[key]?.[order] || "";
                  // 记住排序
                  localStorage.setItem("proxy-pool-sort-field", key);
                  localStorage.setItem("proxy-pool-sort-order", order);
                  setSortField(key);
                  setSortOrder(order);
                }
                store.loadNodes({
                  page: pag.current || 1,
                  page_size: pag.pageSize || 50,
                  search,
                  protocol: protocolFilter,
                  pool: poolFilter,
                  sort: sort || undefined,
                });
              }}
              locale={{ emptyText: <Empty description="暂无节点，请导入订阅或手动添加" /> }}
            />

            {/* 纯净度检测流式结果 */}
            {purityNodeId && purityStream && (
              <Modal
                open={true}
                title="纯净度检测"
                onCancel={() => { setPurityNodeId(null); setPurityStream(null); }}
                footer={null}
                width={600}
              >
                <PurityInline stream={purityStream} />
              </Modal>
            )}

            {/* 导入订阅弹窗 */}
            <Modal open={importOpen} title="导入订阅" onCancel={() => setImportOpen(false)} onOk={handleImport} confirmLoading={importing}>
              <Space direction="vertical" className="w-full">
                <Input
                  placeholder="订阅 URL"
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  prefix={<Link2 className="size-3.5 text-slate-400" />}
                />
                <Input placeholder="名称（可选）" value={importName} onChange={(e) => setImportName(e.target.value)} />
                <Space className="w-full">
                  <Select
                    value={importType}
                    onChange={setImportType}
                    style={{ flex: 1 }}
                    options={[
                      { label: "自动检测", value: "auto" },
                      { label: "Clash YAML", value: "clash_yaml" },
                      { label: "Base64 节点列表", value: "base64" },
                    ]}
                  />
                  <Select
                    value={importPool}
                    onChange={setImportPool}
                    style={{ width: 120 }}
                    options={[
                      { label: "归入反代池", value: "api" },
                      { label: "归入注册机池", value: "register" },
                    ]}
                  />
                </Space>
              </Space>
            </Modal>

            {/* 手动添加弹窗 */}
            <Modal open={addOpen} title="手动添加节点" onCancel={() => setAddOpen(false)} onOk={handleAddNode}>
              <Space direction="vertical" className="w-full">
                <Input placeholder="名称" value={addForm.name} onChange={(e) => setAddForm({ ...addForm, name: e.target.value })} />
                <Space className="w-full">
                  <Select
                    value={addForm.protocol}
                    onChange={(v) => setAddForm({ ...addForm, protocol: v })}
                    options={[
                      { label: "HTTP", value: "http" },
                      { label: "HTTPS", value: "https" },
                      { label: "SOCKS5", value: "socks5" },
                      { label: "SS", value: "ss" },
                      { label: "VMess", value: "vmess" },
                      { label: "Trojan", value: "trojan" },
                    ]}
                    style={{ width: 120 }}
                  />
                  <Input placeholder="服务器" value={addForm.server} onChange={(e) => setAddForm({ ...addForm, server: e.target.value })} style={{ flex: 1 }} />
                  <InputNumber placeholder="端口" value={addForm.port} onChange={(v) => setAddForm({ ...addForm, port: v || 0 })} style={{ width: 100 }} />
                </Space>
                <Space className="w-full">
                  <Input placeholder="用户名（可选）" value={addForm.username} onChange={(e) => setAddForm({ ...addForm, username: e.target.value })} />
                  <Input.Password placeholder="密码（可选）" value={addForm.password} onChange={(e) => setAddForm({ ...addForm, password: e.target.value })} />
                </Space>
              </Space>
            </Modal>
          </motion.div>
        )}

        {/* ── 账号分配 ─────────────────────────────────────── */}
        {section === "assignments" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <div className="selection-bar mb-4">
              <span className="text-sm">
                已分配 <strong>{assignedCount}</strong> / {store.assignments.length} 账号
              </span>
              <span className="text-xs text-slate-400">· 延迟 &lt;</span>
              <InputNumber size="small" style={{ width: 60 }} min={0} max={10000} defaultValue={1500}
                id="max-latency" />
              <span className="text-xs text-slate-400">ms</span>
              <Button
                size="small"
                type="primary"
                icon={<Zap className="size-3.5" />}
                onClick={async () => {
                  const maxLat = Number((document.getElementById("max-latency") as HTMLInputElement)?.value || 1500);
                  const result = await api.balanceAssign("api", maxLat);
                  if (result.ok) {
                    message.success(`已分配 ${result.assigned} 个账号（${result.total_unassigned} 个未分配，${result.nodes_available} 个节点可用）`);
                    await store.loadAll();
                  } else {
                    message.error(result.error || "分配失败");
                  }
                }}
              >
                一键平衡分配
              </Button>
              <div className="flex-1" />
              <Input
                size="small"
                prefix={<Search className="size-3.5 text-slate-400" />}
                placeholder="搜索账号或节点…"
                value={assignSearch}
                onChange={(e) => setAssignSearch(e.target.value)}
                style={{ width: 200 }}
                allowClear
              />
              <Button size="small" icon={<RefreshCcw className="size-3.5" />} onClick={() => store.loadAll()} loading={store.loading}>
                刷新
              </Button>
            </div>

            <Table
              size="small"
              rowKey="account_id"
              columns={assignmentColumns}
              dataSource={filteredAssignments}
              loading={store.loading}
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 个账号` }}
              locale={{ emptyText: <Empty description="暂无账号数据" /> }}
            />
          </motion.div>
        )}
      </div>
    </div>
  );
}

// ── 纯净度流式展示（内嵌在 Modal 中） ─────────────────────────

function PurityInline({ stream }: { stream: Record<string, unknown> }) {
  const done = stream.done as Record<string, unknown> | undefined;
  const ip = stream.ip as Record<string, unknown> | undefined;
  const tls = stream.tls as Record<string, unknown> | undefined;
  const ai = (stream.ai as Array<Record<string, unknown>>) || [];
  const error = stream.error as string | undefined;
  const pending = <span className="text-xs text-slate-400"><Loader className="size-3 animate-spin inline" /> 检测中…</span>;

  if (error) return <div className="text-sm text-red-500">检测失败：{error}</div>;

  return (
    <div className="space-y-3">
      {/* IP */}
      {ip && !ip.error ? (
        <div className="p-2 rounded" style={{ borderLeft: `3px solid ${done ? gradeColors[String(done.grade)] : "#64748b"}` }}>
          <div className="flex items-center gap-2">
            {done && (
              <span className="text-lg font-bold" style={{ color: gradeColors[String(done.grade)] }}>{String(done.score)}</span>
            )}
            <span className="text-sm">{String(ip.query || "")} · {String(ip.country || "")} {String(ip.city || "")}</span>
            {done && <Tag color={gradeColors[String(done.grade)]}>{gradeLabels[String(done.grade)]}</Tag>}
          </div>
          <span className="text-xs text-slate-400">{String(ip.isp || "")}</span>
        </div>
      ) : ip?.error ? (
        <div className="text-sm text-red-500">IP 检测失败：{String(ip.error)}</div>
      ) : pending}

      {/* TLS */}
      <div>
        <span className="text-xs uppercase text-slate-400">TLS 指纹 </span>
        {tls ? (
          <span className="text-sm">{tls._ok ? "✅ 正常" : "❌ 异常"} {tls.ja4 ? `JA4: ${String(tls.ja4).slice(0, 24)}…` : ""}</span>
        ) : pending}
      </div>

      {/* AI */}
      <div>
        <span className="text-xs uppercase text-slate-400">AI 服务可达性</span>
        {ai.length > 0 ? ai.map((svc) => (
          <div key={String(svc.name)} className="text-sm">
            {svc.reachable ? "✅" : "❌"} {String(svc.name)} {svc.reachable ? `${svc.latency_ms}ms` : "不可达"}
          </div>
        )) : pending}
      </div>

      {/* Done */}
      {done && (
        <div className="text-xs text-slate-400">
          检测完成
          {(done.deductions as Array<{ reason: string; points: number }>)?.length > 0 && (
            <div className="mt-1">
              {(done.deductions as Array<{ reason: string; points: number }>).map((d, i) => (
                <div key={i}>{d.reason} <span className="text-red-500">{d.points} 分</span></div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
