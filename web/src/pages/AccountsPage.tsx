import { useEffect, useMemo, useRef, useState } from "react";
import { App, Button, Card, Empty, Input, Modal, Select, Space, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  Copy,
  Database,
  Download,
  Gauge,
  Import,
  KeyRound,
  RefreshCcw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Zap,
} from "lucide-react";
import { motion } from "framer-motion";
import { api } from "../api";
import { useAccountStore } from "../stores/accountStore";
import type { Account, RefreshJobEvent, RefreshJobFailure } from "../types";

function jwtExpiry(accessToken: string): string {
  if (!accessToken) return "-";
  try {
    const parts = accessToken.split(".");
    if (parts.length < 2) return "-";
    let payload = parts[1];
    while (payload.length % 4) payload += "=";
    const decoded = JSON.parse(atob(payload));
    return decoded.exp ? new Date(decoded.exp * 1000).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";
  } catch {}
  return "-";
}

function formatDate(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function StatusPill({ status }: { status?: string }) {
  const map: Record<string, { cls: string; text: string }> = {
    normal: { cls: "pill-normal", text: "正常" },
    abnormal: { cls: "pill-abnormal", text: "异常" },
    limited: { cls: "pill-limited", text: "限流" },
    disabled: { cls: "pill-disabled", text: "禁用" },
  };
  const item = map[status || ""] || { cls: "pill-muted", text: status || "-" };
  return <span className={`status-pill ${item.cls}`}><i className="status-dot" style={{ background: "currentColor" }} />{item.text}</span>;
}

function TokenPill({ ok }: { ok: boolean }) {
  return <span className={`status-pill ${ok ? "pill-valid" : "pill-missing"}`}><i className="status-dot" style={{ background: "currentColor" }} />{ok ? "有效" : "缺失"}</span>;
}

export default function AccountsPage() {
  const store = useAccountStore();
  const { message } = App.useApp();
  const didLoad = useRef(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [exportText, setExportText] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [activeAction, setActiveAction] = useState("");
  const [refreshLogs, setRefreshLogs] = useState<RefreshJobEvent[]>([]);
  const [failedIds, setFailedIds] = useState<string[]>([]);
  const [failedItems, setFailedItems] = useState<RefreshJobFailure[]>([]);
  const [failedAction, setFailedAction] = useState<"quota" | "token">("quota");
  const [logsOpen, setLogsOpen] = useState(true);
  const [tableScrollY, setTableScrollY] = useState(420);

  const { accounts, total, page, pageSize, loading, stats } = store;

  useEffect(() => {
    if (!didLoad.current) {
      didLoad.current = true;
      store.loadAccounts();
      store.loadStats();
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      useAccountStore.setState({ search, statusFilter, page: 1 });
      store.loadAccounts({ page: 1, search, status: statusFilter });
    }, 320);
    return () => window.clearTimeout(timer);
  }, [search, statusFilter]);

  useEffect(() => {
    store.setSelected(selectedRowKeys);
  }, [selectedRowKeys]);

  useEffect(() => {
    const updateHeight = () => setTableScrollY(Math.max(260, window.innerHeight - (logsOpen ? 720 : 560)));
    updateHeight();
    window.addEventListener("resize", updateHeight);
    return () => window.removeEventListener("resize", updateHeight);
  }, [logsOpen]);

  const refresh = async () => {
    await Promise.all([store.loadAccounts(), store.loadStats()]);
  };

  const withAction = async (key: string, run: () => Promise<void>) => {
    setActiveAction(key);
    try {
      await run();
    } finally {
      setActiveAction("");
    }
  };

  const startRefreshJob = async (action: "quota" | "token", ids: string[], label: string) => {
    if (ids.length === 0) {
      message.warning("没有可刷新的账号");
      return;
    }
    setActiveAction(`${action}-job`);
    setRefreshLogs([{ type: "start", action, total: ids.length }]);
    setFailedIds([]);
    setFailedItems([]);
    setFailedAction(action);
    try {
      const job = await api.createRefreshJob(action, ids);
      await new Promise<void>((resolve) => {
        const source = new EventSource(`/api/refresh-jobs/${job.job_id}/events`);
        source.onmessage = (event) => {
          const data = JSON.parse(event.data) as RefreshJobEvent;
          setRefreshLogs((logs) => [data, ...logs].slice(0, 160));
          if (data.type === "done") {
            setFailedIds(data.failed_ids || []);
            setFailedItems(data.failed_items || []);
            source.close();
            message.success(`${label}完成：${data.refreshed || 0} 成功，${data.failed || 0} 失败`);
            refresh().finally(resolve);
          }
        };
        source.onerror = () => {
          source.close();
          message.error("刷新日志连接中断");
          refresh().finally(resolve);
        };
      });
    } finally {
      setActiveAction("");
    }
  };

  const handleImport = async () => {
    await withAction("import", async () => {
      try {
        const accountsToImport = JSON.parse(importText);
        if (!Array.isArray(accountsToImport)) {
          message.error("请输入有效的 JSON 数组");
          return;
        }
        const r = await store.importAccounts(accountsToImport);
        message.success(`导入完成：新增 ${r.added} 个，跳过 ${r.skipped} 个`);
        setImportText("");
        setImportOpen(false);
        await refresh();
      } catch (e) {
        message.error("JSON 解析失败：" + (e as Error).message);
      }
    });
  };

  const handleExport = async () => {
    await withAction("export-selected", async () => {
      const accountsToExport = selectedRowKeys.length > 0 ? await store.exportSelected() : store.accounts;
      setExportText(JSON.stringify(accountsToExport, null, 2));
      setExportOpen(true);
    });
  };

  const handleExportAll = async () => {
    await withAction("export-all", async () => {
      const r = await api.exportAccounts([]);
      setExportText(JSON.stringify(r.accounts, null, 2));
      setExportOpen(true);
      message.success(`已准备导出 ${r.count} 个账号`);
    });
  };

  const handleRenewExpiring = async () => {
    await withAction("renew", async () => {
      const r = await store.renewExpiring();
      setFailedIds(r.errors.map((item) => item.id));
      message.success(`续期完成：${r.refreshed} 成功，${r.failed} 失败，到期队列 ${r.expiring_count} 个`);
      await refresh();
    });
  };

  const handleDelete = () => {
    if (selectedRowKeys.length === 0) {
      message.warning("请先选择账号");
      return;
    }
    Modal.confirm({
      title: `删除 ${selectedRowKeys.length} 个账号？`,
      content: "此操作不可撤销。删除后这些 Token 不会再参与刷新和导出。",
      okText: "确认删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        await withAction("delete", async () => {
          const r = await store.batchDelete();
          message.success(`已删除 ${r.removed} 个账号`);
          setSelectedRowKeys([]);
          store.clearSelection();
          await refresh();
        });
      },
    });
  };

  const exportCount = useMemo(() => {
    try {
      return exportText ? JSON.parse(exportText).length : 0;
    } catch {
      return 0;
    }
  }, [exportText]);

  const statCards = [
    { label: "账号总数", value: stats?.total || 0, note: `当前筛选 ${total} 个`, icon: Database },
    { label: "正常账号", value: stats?.normal || 0, note: "可以参与服务", icon: ShieldCheck },
    { label: "异常账号", value: stats?.abnormal || 0, note: "需要复核或重试", icon: ShieldAlert },
    { label: "限流账号", value: stats?.limited || 0, note: "建议稍后刷新", icon: Gauge },
    { label: "禁用账号", value: stats?.disabled || 0, note: "不参与任务", icon: Trash2 },
    { label: "总配额", value: stats?.total_quota || 0, note: "图片额度剩余合计", icon: Zap },
  ];

  const columns: ColumnsType<Account> = [
    {
      title: "账号",
      dataIndex: "email",
      key: "email",
      width: 260,
      ellipsis: true,
      render: (v: string, record) => (
        <div>
          <div className="code-text font-semibold" title={v}>{v || "-"}</div>
          <div className="mt-1 text-xs text-slate-400">{record.notes || record.oauth_profile || "未标注用途"}</div>
        </div>
      ),
    },
    { title: "状态", dataIndex: "status", key: "status", width: 110, render: (s: string) => <StatusPill status={s} /> },
    {
      title: "配额",
      dataIndex: "quota",
      key: "quota",
      width: 120,
      align: "center",
      render: (v: number, record) => (
        <div>
          <strong className="code-text">{v ?? 0}</strong>
          <div className="mt-1 text-[11px] text-slate-400">{record.quota_reset_at ? `重置 ${formatDate(record.quota_reset_at)}` : "无重置时间"}</div>
        </div>
      ),
    },
    { title: "计划", dataIndex: "plan_type", key: "plan_type", width: 90, render: (v: string) => <span className="text-sm">{v || "-"}</span> },
    { title: "Refresh Token", dataIndex: "refresh_token", key: "refresh_token", width: 140, align: "center", render: (v: string) => <TokenPill ok={Boolean(v)} /> },
    { title: "Token 到期", dataIndex: "access_token", key: "token_expiry", width: 150, render: (v: string) => <span className="text-xs">{jwtExpiry(v)}</span> },
    { title: "最后刷新", dataIndex: "last_refreshed_at", key: "last_refreshed_at", width: 150, render: (v: string) => <span className="text-xs">{formatDate(v)}</span> },
    {
      title: "操作",
      key: "actions",
      width: 132,
      fixed: "right",
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title="刷新 Token">
            <Button type="text" size="small" icon={<KeyRound className="size-4" />} disabled={!record.refresh_token || Boolean(activeAction)} onClick={() => startRefreshJob("token", [record.id], "Token 刷新")} />
          </Tooltip>
          <Tooltip title="刷新配额">
            <Button type="text" size="small" icon={<Gauge className="size-4" />} disabled={!record.access_token || Boolean(activeAction)} onClick={() => startRefreshJob("quota", [record.id], "配额刷新")} />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-stack accounts-page">
      <div className="section-head">
        <div>
          <h2 className="section-title">账号管理</h2>
          <p className="section-desc">刷新操作会输出逐账号日志，失败项可以直接重试。</p>
        </div>
        <Space wrap>
          <Button icon={<Import className="size-4" />} onClick={() => setImportOpen(true)}>导入</Button>
          <Button icon={<RefreshCcw className="size-4" />} loading={activeAction === "renew"} onClick={handleRenewExpiring}>续期到期 Token</Button>
          <Button type="primary" icon={<Gauge className="size-4" />} loading={activeAction === "quota-job"} onClick={() => startRefreshJob("quota", accounts.filter((a) => a.access_token).map((a) => a.id), "配额刷新")}>刷新当前页配额</Button>
          <Button icon={<Download className="size-4" />} loading={activeAction === "export-all"} onClick={handleExportAll}>全部导出</Button>
        </Space>
      </div>

      <div className="metric-grid">
        {statCards.map((item, index) => {
          const Icon = item.icon;
          return (
            <motion.div key={item.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.025 }} className="surface metric-card">
              <div className="metric-label"><span>{item.label}</span><Icon className="size-4" /></div>
              <div className="metric-value">{item.value}</div>
              <div className="metric-note">{item.note}</div>
            </motion.div>
          );
        })}
      </div>

      <Card className="surface token-table-card" styles={{ body: { padding: 0 } }}>
        <div className="toolbar p-4">
          <Input placeholder="搜索邮箱、备注或标签" prefix={<Search className="size-4 text-slate-400" />} value={search} onChange={(e) => setSearch(e.target.value)} allowClear style={{ width: 280 }} />
          <Select
            value={statusFilter || undefined}
            onChange={(v) => setStatusFilter(v || "")}
            placeholder="状态筛选"
            style={{ width: 140 }}
            allowClear
            options={[
              { value: "normal", label: "正常" },
              { value: "abnormal", label: "异常" },
              { value: "limited", label: "限流" },
              { value: "disabled", label: "禁用" },
            ]}
          />
          <Button icon={<RefreshCcw className="size-4" />} onClick={refresh} loading={loading}>刷新列表</Button>
          <div className="toolbar-spacer" />
          <span className="text-sm text-slate-500">共 {total} 个账号</span>
        </div>

        {selectedRowKeys.length > 0 && (
          <motion.div className="selection-bar mx-4 mb-4" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
            <strong className="text-sm">已选择 {selectedRowKeys.length} 个账号</strong>
            <div className="toolbar-spacer" />
            <Button size="small" icon={<KeyRound className="size-3.5" />} loading={activeAction === "token-job"} onClick={() => startRefreshJob("token", selectedRowKeys, "Token 刷新")}>刷新 Token</Button>
            <Button size="small" icon={<Gauge className="size-3.5" />} loading={activeAction === "quota-job"} onClick={() => startRefreshJob("quota", selectedRowKeys, "配额刷新")}>刷新配额</Button>
            <Button size="small" icon={<Download className="size-3.5" />} loading={activeAction === "export-selected"} onClick={handleExport}>导出</Button>
            <Button size="small" danger icon={<Trash2 className="size-3.5" />} loading={activeAction === "delete"} onClick={handleDelete}>删除</Button>
          </motion.div>
        )}

        <Table<Account>
          dataSource={accounts}
          columns={columns}
          rowKey="id"
          loading={loading}
          size="middle"
          rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
          pagination={{
            current: page,
            total,
            pageSize,
            showTotal: (t) => `共 ${t} 个`,
            showSizeChanger: true,
            pageSizeOptions: [20, 50, 100, 200],
            onChange: (p, ps) => store.loadAccounts({ page: p, page_size: ps, search, status: statusFilter }),
          }}
          scroll={{ x: 1120, y: tableScrollY }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search || statusFilter ? "没有匹配的账号" : "暂无账号，先导入或启动注册机"} /> }}
        />
      </Card>

      <Card
        className="surface"
        title="刷新日志"
        extra={
          <Space>
            {failedIds.length > 0 && <Button size="small" danger onClick={() => startRefreshJob(failedAction, failedIds, "失败项重试")}>重试失败项（{failedIds.length}）</Button>}
            <Button size="small" onClick={() => setLogsOpen((value) => !value)}>{logsOpen ? "收起" : "展开"}</Button>
            <Button size="small" onClick={() => setRefreshLogs([])}>清空</Button>
          </Space>
        }
      >
        <FailureGroups
          items={failedItems}
          action={failedAction}
          onSelect={(ids) => {
            setSelectedRowKeys(ids);
            message.success(`已选择 ${ids.length} 个账号`);
          }}
          onRetry={(ids) => startRefreshJob(failedAction, ids, "失败分组重试")}
        />
        {logsOpen ? (
          <RefreshLogList logs={refreshLogs} />
        ) : (
          <div className="accounts-log-collapsed">
            {refreshLogs[0] ? <span>最新日志：{logText(refreshLogs[0])}</span> : <span>暂无刷新日志</span>}
          </div>
        )}
      </Card>

      <Modal title="导入账号 JSON" open={importOpen} onCancel={() => setImportOpen(false)} onOk={handleImport} okText="确认导入" confirmLoading={activeAction === "import"} width={720}>
        <p className="mb-3 text-sm text-slate-500">粘贴账号数组后会自动跳过已存在账号，并保留可识别的 Token 字段。</p>
        <Input.TextArea value={importText} onChange={(e) => setImportText(e.target.value)} placeholder='[{"email":"name@example.com","access_token":"eyJ...","refresh_token":"r_..."}]' rows={10} className="code-text" />
      </Modal>

      <Modal
        title={`导出结果（${exportCount} 个账号）`}
        open={exportOpen}
        onCancel={() => setExportOpen(false)}
        footer={[
          <Button key="copy" icon={<Copy className="size-4" />} onClick={async () => { await navigator.clipboard.writeText(exportText); message.success("导出 JSON 已复制"); }}>复制</Button>,
          <Button key="download" icon={<Download className="size-4" />} onClick={() => {
            const blob = new Blob([exportText], { type: "application/json" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "accounts-export.json";
            a.click();
            URL.revokeObjectURL(a.href);
            message.success("导出文件已生成");
          }}>下载</Button>,
          <Button key="close" onClick={() => setExportOpen(false)}>关闭</Button>,
        ]}
        width={720}
      >
        <Input.TextArea readOnly value={exportText} rows={14} className="code-text" />
      </Modal>
    </div>
  );
}

function logText(log: RefreshJobEvent) {
  if (log.type === "start") return `开始${log.action === "token" ? "刷新 Token" : "刷新配额"}，共 ${log.total || 0} 个账号`;
  if (log.type === "done") return `刷新完成：${log.refreshed || 0} 成功，${log.failed || 0} 失败`;
  if (log.type === "progress" && log.status === "running") return `[${log.email}] 正在刷新`;
  if (log.type === "progress" && log.status === "success") return `[${log.email}] 成功${log.quota !== undefined ? `，配额 ${log.quota}` : ""}${log.plan_type ? `，计划 ${log.plan_type}` : ""}`;
  if (log.type === "progress" && log.status === "failed") return `[${log.email}] 失败：${log.error || "未知错误"}`;
  return "";
}

function groupFailures(items: RefreshJobFailure[]) {
  const grouped = new Map<string, RefreshJobFailure[]>();
  items.forEach((item) => {
    const key = item.error_group || item.error || "未知错误";
    grouped.set(key, [...(grouped.get(key) || []), item]);
  });
  return Array.from(grouped.entries()).map(([group, groupItems]) => ({ group, items: groupItems }));
}

function FailureGroups({ items, action, onSelect, onRetry }: {
  items: RefreshJobFailure[];
  action: "quota" | "token";
  onSelect: (ids: string[]) => void;
  onRetry: (ids: string[]) => void;
}) {
  const groups = groupFailures(items);
  if (groups.length === 0) return null;
  return (
    <div className="mb-4 space-y-3">
      {groups.map(({ group, items: groupItems }) => {
        const ids = groupItems.map((item) => item.id);
        const retryable = groupItems.some((item) => item.retryable);
        return (
          <div key={group} className="selection-bar">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <strong className="text-sm">{group}</strong>
                <Tag color={retryable ? "gold" : "red"}>{retryable ? "可重试" : "需处理账号"}</Tag>
                <span className="text-sm text-slate-500">{groupItems.length} 个账号</span>
              </div>
              <div className="mt-1 truncate text-xs text-slate-500" title={groupItems[0]?.error}>{groupItems[0]?.error}</div>
            </div>
            <div className="toolbar-spacer" />
            <Button size="small" onClick={() => onSelect(ids)}>选择本组</Button>
            <Button size="small" type={retryable ? "primary" : "default"} onClick={() => onRetry(ids)}>
              {action === "token" ? "重试 Token" : "重试配额"}
            </Button>
          </div>
        );
      })}
    </div>
  );
}

function RefreshLogList({ logs }: { logs: RefreshJobEvent[] }) {
  return (
    <div className="log-terminal accounts-log">
      {logs.length === 0 ? (
        <p className="m-0 text-slate-500">暂无刷新日志。执行刷新后会显示每个账号的结果。</p>
      ) : logs.map((log, index) => (
        <div key={index} className={`log-line log-${log.status === "success" ? "green" : log.status === "failed" ? "red" : "yellow"}`}>
          <span className="log-time">{log.type === "done" ? "完成" : `${log.index || 0}/${log.total || 0}`}</span>
          <span>{logText(log)}</span>
        </div>
      ))}
    </div>
  );
}
