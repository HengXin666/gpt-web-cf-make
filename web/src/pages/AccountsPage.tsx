import { useEffect, useMemo, useRef, useState } from "react";
import {
  App,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tooltip,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  BarChart3,
  Copy,
  Database,
  Download,
  Gauge,
  Import,
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
import type { Account } from "../types";

function jwtExpiry(accessToken: string): string {
  if (!accessToken) return "-";
  try {
    const parts = accessToken.split(".");
    if (parts.length < 2) return "-";
    let payload = parts[1];
    while (payload.length % 4) payload += "=";
    const decoded = JSON.parse(atob(payload));
    if (decoded.exp) {
      return new Date(decoded.exp * 1000).toLocaleString("zh-CN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    }
  } catch {}
  return "-";
}

function formatDate(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusPill({ status }: { status?: string }) {
  const map: Record<string, { cls: string; text: string }> = {
    normal: { cls: "pill-normal", text: "正常" },
    abnormal: { cls: "pill-abnormal", text: "异常" },
    limited: { cls: "pill-limited", text: "限流" },
    disabled: { cls: "pill-disabled", text: "禁用" },
  };
  const item = map[status || ""] || { cls: "pill-muted", text: status || "-" };
  return (
    <span className={`status-pill ${item.cls}`}>
      <i className="status-dot" style={{ background: "currentColor" }} />
      {item.text}
    </span>
  );
}

function TokenPill({ ok }: { ok: boolean }) {
  return (
    <span className={`status-pill ${ok ? "pill-valid" : "pill-missing"}`}>
      <i className="status-dot" style={{ background: "currentColor" }} />
      {ok ? "有效" : "缺失"}
    </span>
  );
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
  const [activeAction, setActiveAction] = useState<string>("");

  const { accounts, total, page, loading, stats } = store;

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

  const handleRefreshAllQuota = async () => {
    await withAction("refresh-all-quota", async () => {
      const allIds = store.accounts.filter((a) => a.access_token).map((a) => a.id);
      if (allIds.length === 0) {
        message.warning("当前页没有可刷新配额的账号");
        return;
      }
      store.setSelected(allIds);
      const r = await store.batchRefreshQuota();
      message.success(`全部配额刷新完成：${r.refreshed} 成功，${r.failed} 失败`);
      await refresh();
    });
  };

  const handleBatchRefreshQuota = async () => {
    await withAction("batch-quota", async () => {
      if (selectedRowKeys.length === 0) {
        message.warning("请先选择账号");
        return;
      }
      const r = await store.batchRefreshQuota();
      message.success(`配额刷新完成：${r.refreshed} 成功，${r.failed} 失败`);
      await refresh();
    });
  };

  const handleBatchRefreshToken = async () => {
    await withAction("batch-token", async () => {
      if (selectedRowKeys.length === 0) {
        message.warning("请先选择账号");
        return;
      }
      const r = await store.batchRefresh();
      message.success(`Token 刷新完成：${r.refreshed} 成功，${r.failed} 失败`);
      await refresh();
    });
  };

  const handleRenewExpiring = async () => {
    await withAction("renew", async () => {
      const r = await store.renewExpiring();
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

  const statCards = useMemo(() => {
    const totalCount = stats?.total || 0;
    const pct = (value: number) => (totalCount > 0 ? Math.round((value / totalCount) * 100) : 0);
    return [
      { label: "账号总数", value: totalCount, note: `当前筛选 ${total} 个`, icon: Database, width: 100 },
      { label: "正常 Token", value: stats?.normal || 0, note: `${pct(stats?.normal || 0)}% 健康`, icon: ShieldCheck, width: pct(stats?.normal || 0) },
      { label: "异常账号", value: stats?.abnormal || 0, note: "需要复核", icon: ShieldAlert, width: pct(stats?.abnormal || 0) },
      { label: "限流账号", value: stats?.limited || 0, note: "建议稍后重试", icon: Gauge, width: pct(stats?.limited || 0) },
      { label: "禁用账号", value: stats?.disabled || 0, note: "不参与任务", icon: Trash2, width: pct(stats?.disabled || 0) },
      { label: "总配额", value: stats?.total_quota || 0, note: "可用 Token 预算", icon: Zap, width: Math.min(100, stats?.total_quota || 0) },
    ];
  }, [stats, total]);

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
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (s: string) => <StatusPill status={s} />,
    },
    {
      title: "配额",
      dataIndex: "quota",
      key: "quota",
      width: 130,
      align: "center",
      render: (v: number) => (
        <div>
          <strong className="code-text">{v ?? 0}</strong>
          <div className="meter mx-auto max-w-[82px]"><span style={{ width: `${Math.min(100, Math.max(0, v || 0))}%` }} /></div>
        </div>
      ),
    },
    {
      title: "计划",
      dataIndex: "plan_type",
      key: "plan_type",
      width: 90,
      render: (v: string) => <span className="text-sm">{v || "-"}</span>,
    },
    {
      title: "Refresh Token",
      dataIndex: "refresh_token",
      key: "refresh_token",
      width: 140,
      align: "center",
      render: (v: string) => <TokenPill ok={Boolean(v)} />,
    },
    {
      title: "Token 到期",
      dataIndex: "access_token",
      key: "token_expiry",
      width: 150,
      render: (v: string) => <span className="text-xs">{jwtExpiry(v)}</span>,
    },
    {
      title: "最后刷新",
      dataIndex: "last_refreshed_at",
      key: "last_refreshed_at",
      width: 150,
      render: (v: string) => <span className="text-xs">{formatDate(v)}</span>,
    },
    {
      title: "操作",
      key: "actions",
      width: 128,
      fixed: "right",
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title="刷新 Token">
            <Button
              type="text"
              size="small"
              icon={<RefreshCcw className="size-4" />}
              disabled={!record.refresh_token}
              loading={activeAction === `token-${record.id}`}
              onClick={() => withAction(`token-${record.id}`, async () => {
                const r = await store.refreshToken(record.id);
                r.ok ? message.success("Token 已刷新") : message.error("Token 刷新失败");
                await refresh();
              })}
            />
          </Tooltip>
          <Tooltip title="刷新配额">
            <Button
              type="text"
              size="small"
              icon={<BarChart3 className="size-4" />}
              disabled={!record.access_token}
              loading={activeAction === `quota-${record.id}`}
              onClick={() => withAction(`quota-${record.id}`, async () => {
                const r = await store.refreshQuota(record.id);
                r.ok ? message.success("配额已刷新") : message.error("配额刷新失败");
                await refresh();
              })}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <div className="section-head">
        <div>
          <h2 className="section-title">Token 资产总览</h2>
          <p className="section-desc">用健康状态、配额和到期时间判断哪些账号可以继续参与服务。</p>
        </div>
        <Space wrap>
          <Button icon={<Import className="size-4" />} onClick={() => setImportOpen(true)}>
            导入
          </Button>
          <Button
            icon={<RefreshCcw className="size-4" />}
            loading={activeAction === "renew"}
            onClick={handleRenewExpiring}
          >
            续期到期 Token
          </Button>
          <Button
            type="primary"
            icon={<BarChart3 className="size-4" />}
            loading={activeAction === "refresh-all-quota"}
            onClick={handleRefreshAllQuota}
          >
            刷新全部配额
          </Button>
          <Button
            icon={<Download className="size-4" />}
            loading={activeAction === "export-all"}
            onClick={handleExportAll}
          >
            全部导出
          </Button>
        </Space>
      </div>

      <div className="metric-grid">
        {statCards.map((item, index) => {
          const Icon = item.icon;
          return (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.035, duration: 0.2 }}
              className="surface metric-card"
            >
              <div className="metric-label">
                <span>{item.label}</span>
                <Icon className="size-4" />
              </div>
              <div className="metric-value">{item.value}</div>
              <div className="metric-note">{item.note}</div>
              <div className="meter"><span style={{ width: `${item.width}%` }} /></div>
            </motion.div>
          );
        })}
      </div>

      <Card className="surface token-table-card" styles={{ body: { padding: 0 } }}>
        <div className="toolbar p-4">
          <Input
            placeholder="搜索邮箱、备注或标签"
            prefix={<Search className="size-4 text-slate-400" />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
            style={{ width: 280 }}
          />
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
          <Button icon={<RefreshCcw className="size-4" />} onClick={refresh} loading={loading}>
            刷新列表
          </Button>
          <div className="toolbar-spacer" />
          <span className="text-sm text-slate-500">共 {total} 个账号</span>
        </div>

        {selectedRowKeys.length > 0 && (
          <motion.div
            className="selection-bar mx-4 mb-4"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <strong className="text-sm">已选择 {selectedRowKeys.length} 个账号</strong>
            <div className="toolbar-spacer" />
            <Button
              size="small"
              icon={<RefreshCcw className="size-3.5" />}
              loading={activeAction === "batch-token"}
              onClick={handleBatchRefreshToken}
            >
              刷新 Token
            </Button>
            <Button
              size="small"
              icon={<BarChart3 className="size-3.5" />}
              loading={activeAction === "batch-quota"}
              onClick={handleBatchRefreshQuota}
            >
              刷新配额
            </Button>
            <Button
              size="small"
              icon={<Download className="size-3.5" />}
              loading={activeAction === "export-selected"}
              onClick={handleExport}
            >
              导出
            </Button>
            <Button
              size="small"
              danger
              icon={<Trash2 className="size-3.5" />}
              loading={activeAction === "delete"}
              onClick={handleDelete}
            >
              删除
            </Button>
          </motion.div>
        )}

        <Table<Account>
          dataSource={accounts}
          columns={columns}
          rowKey="id"
          loading={loading}
          size="middle"
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as string[]),
          }}
          pagination={{
            current: page,
            total,
            pageSize: 50,
            showTotal: (t) => `共 ${t} 个`,
            showSizeChanger: false,
            onChange: (p) => store.loadAccounts({ page: p, search, status: statusFilter }),
          }}
          scroll={{ x: 1120 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={search || statusFilter ? "没有匹配的账号" : "暂无账号，先导入或启动注册机"}
              />
            ),
          }}
        />
      </Card>

      <Modal
        title="导入账号 JSON"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={handleImport}
        okText="确认导入"
        confirmLoading={activeAction === "import"}
        width={720}
      >
        <p className="mb-3 text-sm text-slate-500">粘贴账号数组后会自动跳过已存在账号，并保留可识别的 Token 字段。</p>
        <Input.TextArea
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder='[{"email":"name@example.com","access_token":"eyJ...","refresh_token":"r_..."}]'
          rows={10}
          className="code-text"
        />
      </Modal>

      <Modal
        title={`导出结果（${exportCount} 个账号）`}
        open={exportOpen}
        onCancel={() => setExportOpen(false)}
        footer={[
          <Button
            key="copy"
            icon={<Copy className="size-4" />}
            onClick={async () => {
              await navigator.clipboard.writeText(exportText);
              message.success("导出 JSON 已复制");
            }}
          >
            复制
          </Button>,
          <Button
            key="download"
            icon={<Download className="size-4" />}
            onClick={() => {
              const blob = new Blob([exportText], { type: "application/json" });
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = "accounts-export.json";
              a.click();
              URL.revokeObjectURL(a.href);
              message.success("导出文件已生成");
            }}
          >
            下载
          </Button>,
          <Button key="close" onClick={() => setExportOpen(false)}>关闭</Button>,
        ]}
        width={720}
      >
        <Input.TextArea readOnly value={exportText} rows={14} className="code-text" />
      </Modal>
    </div>
  );
}
