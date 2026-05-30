/** 后端 API 客户端 */

const BASE = "";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(`${BASE}${path}`, opts);
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  }
  return resp.json() as Promise<T>;
}

// ── 账号管理 ──

import type {
  Account,
  AccountListResponse,
  AccountStats,
  BatchResult,
  RefreshJob,
} from "./types";

export const api = {
  // 账号
  listAccounts(params: {
    page?: number;
    page_size?: number;
    status?: string;
    search?: string;
    tags?: string;
    sort?: string;
  } = {}) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v) qs.set(k, String(v));
    });
    return request<AccountListResponse>("GET", `/api/accounts?${qs.toString()}`);
  },

  getAccountStats() {
    return request<AccountStats>("GET", "/api/accounts/stats");
  },

  getAccount(id: string) {
    return request<Account>("GET", `/api/accounts/${id}`);
  },

  importAccounts(accounts: Array<Record<string, unknown>>) {
    return request<{ added: number; skipped: number }>("POST", "/api/accounts/import", { accounts });
  },

  exportAccounts(ids: string[]) {
    return request<{ accounts: Account[]; count: number }>("POST", "/api/accounts/export", { ids });
  },

  exportErrors(accounts: Array<Record<string, unknown>>) {
    return request<{ file: string; count: number; total: number }>("POST", "/api/accounts/export-errors", { accounts });
  },

  batchDelete(ids: string[]) {
    return request<{ removed: number }>("POST", "/api/accounts/batch-delete", { ids });
  },

  batchRefreshQuota(ids: string[]) {
    return request<BatchResult>("POST", "/api/accounts/batch-refresh-quota", { ids });
  },

  refreshQuota(id: string) {
    return request<{ ok: boolean; error?: string }>("POST", `/api/accounts/${id}/refresh-quota`);
  },

  updateAccount(id: string, updates: { tags?: string[]; notes?: string; status?: string }) {
    return request<Account>("PATCH", `/api/accounts/${id}`, updates);
  },

  // Token
  refreshToken(id: string) {
    return request<{ ok: boolean; error?: string }>("POST", `/api/tokens/refresh/${id}`);
  },

  batchRefreshTokens(ids: string[]) {
    return request<BatchResult>("POST", "/api/tokens/batch-refresh", { ids });
  },

  renewExpiring() {
    return request<BatchResult & { expiring_count: number }>("POST", "/api/tokens/renew-expiring");
  },

  getTokenStats() {
    return request<import("./types").TokenStats>("GET", "/api/tokens/stats");
  },

  // 注册机
  getRegisterConfig() {
    return request<import("./types").RegisterConfig>("GET", "/api/register/config");
  },

  updateRegisterConfig(updates: Record<string, unknown>) {
    return request<import("./types").RegisterConfig>("PUT", "/api/register/config", updates);
  },

  startRegister() {
    return request<import("./types").RegisterConfig>("POST", "/api/register/start");
  },

  stopRegister() {
    return request<import("./types").RegisterConfig>("POST", "/api/register/stop");
  },

  resetRegister() {
    return request<import("./types").RegisterConfig>("POST", "/api/register/reset");
  },

  // 设置
  getSettings() {
    return request<import("./types").AppConfig>("GET", "/api/settings");
  },

  updateSettings(updates: Record<string, unknown>) {
    return request<import("./types").AppConfig>("PUT", "/api/settings", updates);
  },

  testProxy(proxy: string, url?: string) {
    return request<import("./types").ProxyTestResult>("POST", "/api/settings/test-proxy", { proxy, url });
  },

  async *checkProxyPurityStream(proxy: string): AsyncGenerator<{ step: string; [key: string]: unknown }> {
    const resp = await fetch("/api/proxy/check-purity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proxy }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop()!;
      for (const line of lines) {
        if (line.trim()) {
          try {
            yield JSON.parse(line);
          } catch { /* skip */ }
        }
      }
    }
  },

  createRefreshJob(action: "quota" | "token", ids: string[]) {
    return request<RefreshJob>("POST", "/api/refresh-jobs", { action, ids });
  },

  getUpstreamModels(upstreamBaseUrl?: string) {
    const qs = new URLSearchParams();
    if (upstreamBaseUrl) qs.set("upstream_base_url", upstreamBaseUrl);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<import("./types").UpstreamModelsResult>("GET", `/api/settings/upstream-models${suffix}`);
  },

  // OpenAI 兼容反代
  getProxyStatus() {
    return request<import("./types").ProxyStatus>("GET", "/api/proxy/status");
  },

  listProxyKeys() {
    return request<{ items: import("./types").ProxyKey[] }>("GET", "/api/proxy/keys");
  },

  createProxyKey(name: string) {
    return request<import("./types").ProxyKeyCreated>("POST", "/api/proxy/keys", { name });
  },

  updateProxyKey(id: string, updates: { name?: string; enabled?: boolean }) {
    return request<import("./types").ProxyKey>("PATCH", `/api/proxy/keys/${id}`, updates);
  },

  deleteProxyKey(id: string) {
    return request<{ deleted: boolean }>("DELETE", `/api/proxy/keys/${id}`);
  },

  getProxyUsage(limit = 5000) {
    return request<import("./types").ProxyUsageSummary>("GET", `/api/proxy/usage?limit=${limit}`);
  },

  getProxyUsageAccounts(limit = 5000) {
    return request<import("./types").ProxyUsageAccountSummary>("GET", `/api/proxy/usage-accounts?limit=${limit}`);
  },

  getProxyUsageSeries(minutes = 240, bucketSeconds = 60) {
    return request<import("./types").ProxyUsageSeries>("GET", `/api/proxy/usage-series?minutes=${minutes}&bucket_seconds=${bucketSeconds}`);
  },

  // ── 代理池 ──

  listProxyNodes(params: { enabled?: boolean; search?: string; protocol?: string; pool?: string; sort?: string; page?: number; page_size?: number } = {}) {
    const qs = new URLSearchParams();
    if (params.enabled !== undefined) qs.set("enabled", String(params.enabled));
    if (params.search) qs.set("search", params.search);
    if (params.protocol) qs.set("protocol", params.protocol);
    if (params.pool) qs.set("pool", params.pool);
    if (params.sort) qs.set("sort", params.sort);
    if (params.page) qs.set("page", String(params.page));
    if (params.page_size) qs.set("page_size", String(params.page_size));
    return request<import("./types").ProxyNodeListResponse>("GET", `/api/proxy-pool/nodes?${qs.toString()}`);
  },

  getProxyNode(id: string) {
    return request<import("./types").ProxyNode>("GET", `/api/proxy-pool/nodes/${id}`);
  },

  addProxyNodes(items: Array<Record<string, unknown>>) {
    return request<{ added: number; skipped: number }>("POST", "/api/proxy-pool/nodes", { items });
  },

  updateProxyNode(id: string, updates: Record<string, unknown>) {
    return request<import("./types").ProxyNode>("PATCH", `/api/proxy-pool/nodes/${id}`, updates);
  },

  deleteProxyNodes(ids: string[]) {
    return request<{ removed: number }>("DELETE", "/api/proxy-pool/nodes", { ids });
  },

  batchSetProxyPool(ids: string[], pool: string) {
    return request<{ ok: boolean; changed?: number; error?: string }>("POST", "/api/proxy-pool/nodes/batch-set-pool", { ids, pool });
  },

  listProxySubscriptions() {
    return request<import("./types").ProxySubscription[]>("GET", "/api/proxy-pool/subscriptions");
  },

  importProxySubscription(url: string, name = "", type = "auto", pool = "api") {
    return request<{ ok: boolean; error?: string; subscription_id?: string; name?: string; total_parsed?: number; added?: number; updated?: number }>(
      "POST", "/api/proxy-pool/subscriptions", { url, name, type, pool }
    );
  },

  syncProxySubscription(id: string) {
    return request<{ ok: boolean; error?: string }>("POST", `/api/proxy-pool/subscriptions/${id}/sync`);
  },

  syncAllProxySubscriptions() {
    return request<{ synced: number; total: number }>("POST", "/api/proxy-pool/subscriptions/sync-all");
  },

  deleteProxySubscription(id: string) {
    return request<{ ok: boolean; removed_nodes?: number }>("DELETE", `/api/proxy-pool/subscriptions/${id}`);
  },

  testProxyNode(id: string) {
    return request<{ ok: boolean; latency_ms?: number; status?: number; error?: string }>("POST", `/api/proxy-pool/nodes/${id}/test`);
  },

  async *testProxyNodePurity(id: string): AsyncGenerator<{ step: string; [key: string]: unknown }> {
    const resp = await fetch(`/api/proxy-pool/nodes/${id}/test-purity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop()!;
      for (const line of lines) {
        if (line.trim()) {
          try { yield JSON.parse(line); } catch { /* skip */ }
        }
      }
    }
  },

  batchTestProxyNodes(ids: string[], maxWorkers = 5, autoDisable = true) {
    return request<{ tested: number; failed: number; disabled: number; results: Array<Record<string, unknown>> }>(
      "POST", "/api/proxy-pool/nodes/batch-test", { ids, max_workers: maxWorkers, auto_disable: autoDisable }
    );
  },

  testProxyNodeGpt(id: string) {
    return request<{ ok: boolean; gpt_results?: Record<string, unknown>; auto_disabled?: boolean; error?: string }>(
      "POST", `/api/proxy-pool/nodes/${id}/test-gpt`
    );
  },

  getProxyAssignments() {
    return request<import("./types").ProxyAssignment[]>("GET", "/api/proxy-pool/assignments");
  },

  assignProxyNode(accountId: string, nodeId: string) {
    return request<{ ok: boolean; error?: string }>("POST", "/api/proxy-pool/assign", { account_id: accountId, node_id: nodeId });
  },

  unassignProxyNode(accountId: string) {
    return request<{ ok: boolean }>("DELETE", `/api/proxy-pool/assign/${accountId}`);
  },

  balanceAssign(pool = "api", max_latency_ms = 1500, min_score = 0) {
    return request<{ ok: boolean; assigned?: number; total_unassigned?: number; nodes_available?: number; error?: string }>(
      "POST", "/api/proxy-pool/balance-assign", { pool, max_latency_ms, min_score }
    );
  },

  getProxyPoolStats() {
    return request<import("./types").ProxyPoolStats>("GET", "/api/proxy-pool/stats");
  },

  getProxyAutoRefresh() {
    return request<{ enabled: boolean; interval_minutes: number; running: boolean }>("GET", "/api/proxy-pool/auto-refresh");
  },

  updateProxyAutoRefresh(enabled: boolean, intervalMinutes = 60) {
    return request<{ enabled: boolean; interval_minutes: number; running: boolean }>("POST", "/api/proxy-pool/auto-refresh", { enabled, interval_minutes: intervalMinutes });
  },
};
