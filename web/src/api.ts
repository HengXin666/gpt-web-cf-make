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

  getProxyUsageSeries(minutes = 240, bucketSeconds = 60) {
    return request<import("./types").ProxyUsageSeries>("GET", `/api/proxy/usage-series?minutes=${minutes}&bucket_seconds=${bucketSeconds}`);
  },
};
