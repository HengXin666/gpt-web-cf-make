import { create } from "zustand";
import type { ProxyNode, ProxySubscription, ProxyPoolStats, ProxyAssignment } from "../types";
import { api } from "../api";

interface ProxyPoolStore {
  nodes: ProxyNode[];
  subscriptions: ProxySubscription[];
  stats: ProxyPoolStats | null;
  assignments: ProxyAssignment[];
  loading: boolean;
  testing: Set<string>;
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;

  loadNodes: (params?: { enabled?: boolean; search?: string; protocol?: string; pool?: string; sort?: string; page?: number; page_size?: number }) => Promise<void>;
  loadSubscriptions: () => Promise<void>;
  loadStats: () => Promise<void>;
  loadAssignments: () => Promise<void>;
  loadAll: () => Promise<void>;

  addNodes: (items: Array<Record<string, unknown>>) => Promise<{ added: number; skipped: number }>;
  updateNode: (id: string, updates: Record<string, unknown>) => Promise<void>;
  deleteNodes: (ids: string[]) => Promise<{ removed: number }>;

  importSubscription: (url: string, name?: string, type?: string, pool?: string) => Promise<{ ok: boolean; error?: string; added?: number; updated?: number; total_parsed?: number }>;
  syncSubscription: (id: string) => Promise<{ ok: boolean; error?: string }>;
  syncAllSubscriptions: () => Promise<{ synced: number; total: number }>;
  removeSubscription: (id: string) => Promise<{ ok: boolean }>;

  testNode: (id: string) => Promise<{ ok: boolean; latency_ms?: number; error?: string }>;
  batchTest: (ids: string[], maxWorkers?: number) => Promise<{ tested: number; failed: number; disabled: number }>;
  batchSetPool: (ids: string[], pool: string) => Promise<{ ok: boolean; changed?: number }>;

  assignNode: (accountId: string, nodeId: string) => Promise<{ ok: boolean; error?: string }>;
  unassignNode: (accountId: string) => Promise<{ ok: boolean }>;
}

export const useProxyPoolStore = create<ProxyPoolStore>((set, get) => ({
  nodes: [],
  subscriptions: [],
  stats: null,
  assignments: [],
  loading: false,
  testing: new Set(),
  total: 0,
  page: 1,
  pageSize: 50,
  totalPages: 1,

  loadNodes: async (params = {}) => {
    set({ loading: true });
    try {
      const data = await api.listProxyNodes({
        page: params.page ?? get().page,
        page_size: params.page_size ?? get().pageSize,
        ...params,
      });
      set({
        nodes: data.items,
        total: data.total,
        page: data.page,
        pageSize: data.page_size,
        totalPages: data.total_pages,
      });
    } finally {
      set({ loading: false });
    }
  },

  loadSubscriptions: async () => {
    const subscriptions = await api.listProxySubscriptions();
    set({ subscriptions });
  },

  loadStats: async () => {
    const stats = await api.getProxyPoolStats();
    set({ stats });
  },

  loadAssignments: async () => {
    const assignments = await api.getProxyAssignments();
    set({ assignments });
  },

  loadAll: async () => {
    set({ loading: true });
    try {
      const [nodeData, subscriptions, stats, assignments] = await Promise.all([
        api.listProxyNodes({ page: get().page, page_size: get().pageSize }),
        api.listProxySubscriptions(),
        api.getProxyPoolStats(),
        api.getProxyAssignments(),
      ]);
      set({
        nodes: nodeData.items,
        total: nodeData.total,
        page: nodeData.page,
        pageSize: nodeData.page_size,
        totalPages: nodeData.total_pages,
        subscriptions, stats, assignments,
      });
    } finally {
      set({ loading: false });
    }
  },

  addNodes: async (items) => {
    const result = await api.addProxyNodes(items);
    await get().loadNodes();
    await get().loadStats();
    return result;
  },

  updateNode: async (id, updates) => {
    await api.updateProxyNode(id, updates);
    await get().loadNodes();
  },

  deleteNodes: async (ids) => {
    const result = await api.deleteProxyNodes(ids);
    await get().loadNodes();
    await get().loadStats();
    return result;
  },

  importSubscription: async (url, name = "", type = "auto", pool = "api") => {
    const result = await api.importProxySubscription(url, name, type, pool);
    if (result.ok) {
      await get().loadAll();
    }
    return result;
  },

  syncSubscription: async (id) => {
    const result = await api.syncProxySubscription(id);
    if (result.ok) {
      await get().loadAll();
    }
    return result;
  },

  syncAllSubscriptions: async () => {
    const result = await api.syncAllProxySubscriptions();
    await get().loadAll();
    return result;
  },

  removeSubscription: async (id) => {
    const result = await api.deleteProxySubscription(id);
    if (result.ok) {
      await get().loadAll();
    }
    return { ok: result.ok };
  },

  testNode: async (id) => {
    const testing = new Set(get().testing);
    testing.add(id);
    set({ testing });
    try {
      const result = await api.testProxyNode(id);
      // 刷新该节点数据
      await get().loadNodes();
      return result;
    } finally {
      const next = new Set(get().testing);
      next.delete(id);
      set({ testing: next });
    }
  },

  batchTest: async (ids, maxWorkers = 5) => {
    set({ testing: new Set(ids) });
    try {
      const result = await api.batchTestProxyNodes(ids, maxWorkers);
      await get().loadNodes();
      return { tested: result.tested, failed: result.failed, disabled: result.disabled };
    } finally {
      set({ testing: new Set() });
    }
  },

  batchSetPool: async (ids, pool) => {
    const result = await api.batchSetProxyPool(ids, pool);
    if (result.ok) {
      await get().loadNodes();
      await get().loadStats();
    }
    return result;
  },

  assignNode: async (accountId, nodeId) => {
    const result = await api.assignProxyNode(accountId, nodeId);
    if (result.ok) {
      await get().loadAssignments();
    }
    return result;
  },

  unassignNode: async (accountId) => {
    const result = await api.unassignProxyNode(accountId);
    if (result.ok) {
      await get().loadAssignments();
    }
    return result;
  },
}));
