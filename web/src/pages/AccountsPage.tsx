import { useEffect, useRef, useCallback, useState } from "react";
import {
  Table, Card, Button, Input, Select, Tag, Space, Tooltip, Modal, App,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  UploadOutlined, DownloadOutlined, ReloadOutlined,
  BarChartOutlined, DeleteOutlined, SyncOutlined,
  SearchOutlined, CopyOutlined,
} from "@ant-design/icons";
import { useAccountStore } from "../stores/accountStore";
import { api } from "../api";
import type { Account } from "../types";

/** 解码 JWT access_token 获取 exp 过期时间 */
function jwtExpiry(accessToken: string): string {
  if (!accessToken) return "-";
  try {
    const parts = accessToken.split(".");
    if (parts.length < 2) return "-";
    let payload = parts[1];
    while (payload.length % 4) payload += "=";
    const decoded = JSON.parse(atob(payload));
    if (decoded.exp) {
      return new Date(decoded.exp * 1000).toLocaleDateString("zh-CN", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      });
    }
  } catch {}
  return "-";
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

  useEffect(() => {
    if (!didLoad.current) { didLoad.current = true; store.loadAccounts(); store.loadStats(); }
  }, []);

  const refresh = useCallback(() => { store.loadAccounts(); store.loadStats(); }, []);

  // 同步选中状态到 store
  useEffect(() => { store.setSelected(selectedRowKeys); }, [selectedRowKeys]);

  const handleImport = async () => {
    try {
      const accounts = JSON.parse(importText);
      if (!Array.isArray(accounts)) { message.error("请输入有效的 JSON 数组"); return; }
      const r = await store.importAccounts(accounts);
      message.success(`导入: 新增 ${r.added}, 跳过 ${r.skipped}`);
      setImportText(""); setImportOpen(false); refresh();
    } catch (e) { message.error("JSON 解析失败: " + (e as Error).message); }
  };

  // 导出选中
  const handleExport = async () => {
    const ids = selectedRowKeys.length > 0 ? selectedRowKeys : undefined;
    const accounts = ids ? await store.exportSelected() : store.accounts;
    setExportText(JSON.stringify(accounts, null, 2));
    setExportOpen(true);
  };

  // 一键导出全部
  const handleExportAll = async () => {
    const r = await api.exportAccounts([]);
    setExportText(JSON.stringify(r.accounts, null, 2));
    setExportOpen(true);
  };

  // 一键刷新全部配额
  const handleRefreshAllQuota = async () => {
    const allIds = store.accounts.filter(a => a.access_token).map(a => a.id);
    if (allIds.length === 0) { message.warning("没有可刷新的账号"); return; }
    store.setSelected(allIds);
    const r = await store.batchRefreshQuota();
    if (r) message.success(`全部配额刷新: ${r.refreshed} 成功, ${r.failed} 失败`);
    refresh();
  };

  const handleBatchRefreshQuota = async () => {
    if (selectedRowKeys.length === 0) { message.warning("请先选择账号"); return; }
    const r = await store.batchRefreshQuota();
    if (r) message.success(`配额刷新: ${r.refreshed} 成功, ${r.failed} 失败`);
    refresh();
  };

  const handleBatchRefreshToken = async () => {
    if (selectedRowKeys.length === 0) { message.warning("请先选择账号"); return; }
    const r = await store.batchRefresh();
    message.success(`Token 刷新: ${r.refreshed} 成功, ${r.failed} 失败`);
    refresh();
  };

  const handleRenewExpiring = async () => {
    const r = await store.renewExpiring();
    message.success(`续期: ${r.refreshed} 成功, ${r.failed} 失败 (到期 ${r.expiring_count} 个)`);
    refresh();
  };

  const handleDelete = () => {
    if (selectedRowKeys.length === 0) { message.warning("请先选择账号"); return; }
    Modal.confirm({
      title: `确定删除 ${selectedRowKeys.length} 个账号？`,
      content: "此操作不可撤销。",
      okText: "确认删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        const r = await store.batchDelete();
        message.success(`删除: ${r.removed} 个`);
        setSelectedRowKeys([]); store.clearSelection(); refresh();
      },
    });
  };

  const stats = store.stats;
  const { accounts, total, page, loading } = store;

  const columns: ColumnsType<Account> = [
    { title: "邮箱", dataIndex: "email", key: "email", width: 240, ellipsis: true,
      render: (v: string) => <span className="font-mono text-xs" title={v}>{v || "-"}</span> },
    { title: "状态", dataIndex: "status", key: "status", width: 80,
      render: (s: string) => {
        const m: Record<string, { color: string; text: string }> = {
          normal: { color: "green", text: "正常" }, abnormal: { color: "red", text: "异常" },
          limited: { color: "orange", text: "限流" }, disabled: { color: "default", text: "禁用" },
        };
        const c = m[s] || { color: "default", text: s || "-" };
        return <Tag color={c.color}>{c.text}</Tag>;
      } },
    { title: "配额", dataIndex: "quota", key: "quota", width: 60, align: "center",
      render: (v: number) => <span className="font-mono text-xs">{v}</span> },
    { title: "计划", dataIndex: "plan_type", key: "plan_type", width: 80,
      render: (v: string) => v || "-" },
    { title: "Refresh Token", dataIndex: "refresh_token", key: "refresh_token", width: 90, align: "center",
      render: (v: string) => v ? <Tag color="green">有效</Tag> : <Tag color="red">缺失</Tag> },
    { title: "Token 到期", dataIndex: "access_token", key: "token_expiry", width: 130,
      render: (v: string) => <span className="text-xs">{jwtExpiry(v)}</span> },
    { title: "最后刷新", dataIndex: "last_refreshed_at", key: "last_refreshed_at", width: 130,
      render: (v: string) => v ? new Date(v).toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-" },
    { title: "操作", key: "actions", width: 120, fixed: "right",
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="刷新Token"><Button type="link" size="small" icon={<ReloadOutlined />}
            disabled={!record.refresh_token} onClick={() => store.refreshToken(record.id)} /></Tooltip>
          <Tooltip title="刷新配额"><Button type="link" size="small" icon={<BarChartOutlined />}
            disabled={!record.access_token} onClick={() => store.refreshQuota(record.id)} /></Tooltip>
        </Space>
      ) },
  ];

  return (
    <div className="space-y-4">
      {/* 标题栏 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">账号管理</h1>
          <p className="text-sm text-gray-500">管理所有 Token 账号，支持批量刷新、续期、导入导出</p>
        </div>
        <Space>
          <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>导入</Button>
          <Button icon={<SyncOutlined />} onClick={handleRenewExpiring} loading={loading}>续期到期Token</Button>
          <Tooltip title="一键刷新当前页所有账号的配额和状态">
            <Button icon={<BarChartOutlined />} type="primary" loading={loading}
              onClick={handleRefreshAllQuota}>刷新全部配额</Button>
          </Tooltip>
          <Button icon={<DownloadOutlined />} onClick={handleExportAll}>全部导出</Button>
        </Space>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {[
            ["总数", stats.total, "text-gray-600"],
            ["正常", stats.normal, "text-green-600"],
            ["异常", stats.abnormal, "text-red-600"],
            ["限流", stats.limited, "text-orange-600"],
            ["禁用", stats.disabled, "text-gray-400"],
            ["总配额", stats.total_quota, "text-blue-600"],
          ].map(([label, value, cls]) => (
            <Card key={label as string} size="small">
              <div className="text-xs text-gray-500">{label as string}</div>
              <div className={`text-xl font-bold ${cls}`}>{value as number}</div>
            </Card>
          ))}
        </div>
      )}

      {/* 筛选 + 选中批量操作 */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="搜索邮箱或备注..."
          prefix={<SearchOutlined className="text-gray-400" />}
          value={search}
          onChange={(e) => { setSearch(e.target.value); useAccountStore.setState({ search: e.target.value }); }}
          onPressEnter={() => store.loadAccounts({ search })}
          style={{ width: 240 }}
          allowClear
        />
        <Select value={statusFilter || undefined} onChange={(v) => { setStatusFilter(v || ""); store.loadAccounts({ status: v || "" }); }}
          placeholder="状态筛选" style={{ width: 120 }} allowClear>
          <Select.Option value="">全部</Select.Option>
          <Select.Option value="normal">正常</Select.Option>
          <Select.Option value="abnormal">异常</Select.Option>
          <Select.Option value="limited">限流</Select.Option>
          <Select.Option value="disabled">禁用</Select.Option>
        </Select>
        <div className="flex-1" />
        {/* 选中项操作 */}
        <span className="text-sm text-gray-500">
          已选 {selectedRowKeys.length} 项
        </span>
        <Space.Compact>
          <Tooltip title="刷新选中Token"><Button icon={<ReloadOutlined />} size="small" loading={loading}
            disabled={selectedRowKeys.length === 0} onClick={handleBatchRefreshToken}>Token</Button></Tooltip>
          <Tooltip title="刷新选中配额"><Button icon={<BarChartOutlined />} size="small" loading={loading}
            disabled={selectedRowKeys.length === 0} onClick={handleBatchRefreshQuota}>配额</Button></Tooltip>
          <Tooltip title="导出选中"><Button icon={<DownloadOutlined />} size="small"
            disabled={selectedRowKeys.length === 0} onClick={handleExport}>导出</Button></Tooltip>
          <Tooltip title="删除选中"><Button icon={<DeleteOutlined />} size="small" danger
            disabled={selectedRowKeys.length === 0} onClick={handleDelete}>删除</Button></Tooltip>
        </Space.Compact>
      </div>

      {/* 表格 */}
      <Table<Account>
        dataSource={accounts}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
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
          onChange: (p) => store.loadAccounts({ page: p }),
        }}
        scroll={{ x: 900 }}
        locale={{ emptyText: "暂无账号" }}
      />

      {/* 导入 Modal */}
      <Modal title="导入账号 (JSON 数组)" open={importOpen} onCancel={() => setImportOpen(false)}
        onOk={handleImport} okText="确认导入" width={600}>
        <Input.TextArea value={importText} onChange={(e) => setImportText(e.target.value)}
          placeholder='[{"email":"xxx","access_token":"eyJ...","refresh_token":"r_..."}]'
          rows={8} className="font-mono text-xs" />
      </Modal>

      {/* 导出 Modal */}
      <Modal title={`导出结果 (${exportText ? JSON.parse(exportText).length : 0} 个账号)`} open={exportOpen}
        onCancel={() => setExportOpen(false)} footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => navigator.clipboard.writeText(exportText)}>复制</Button>,
          <Button key="download" icon={<DownloadOutlined />} onClick={() => {
            const blob = new Blob([exportText], { type: "application/json" });
            const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
            a.download = "accounts-export.json"; a.click();
          }}>下载</Button>,
          <Button key="close" onClick={() => setExportOpen(false)}>关闭</Button>,
        ]} width={600}>
        <Input.TextArea readOnly value={exportText} rows={12} className="font-mono text-xs" />
      </Modal>
    </div>
  );
}
