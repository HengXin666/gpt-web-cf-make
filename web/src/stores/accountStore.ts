import { create } from "zustand";
import type { Account, AccountStats, BatchResult } from "../types";
import { api } from "../api";

interface AccountStore {
  accounts: Account[];
  stats: AccountStats | null;
  selectedIds: Set<string>;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  loading: boolean;
  statusFilter: string;
  search: string;
  sort: string;

  loadAccounts: (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    search?: string;
    sort?: string;
  }) => Promise<void>;
  loadStats: () => Promise<void>;
  setSelected: (ids: string[]) => void;
  toggleSelect: (id: string) => void;
  selectAll: () => void;
  clearSelection: () => void;
  batchDelete: () => Promise<{ removed: number }>;
  batchRefresh: () => Promise<BatchResult>;
  batchRefreshQuota: () => Promise<BatchResult>;
  refreshToken: (id: string) => Promise<{ ok: boolean }>;
  refreshQuota: (id: string) => Promise<{ ok: boolean }>;
  renewExpiring: () => Promise<BatchResult & { expiring_count: number }>;
  importAccounts: (accounts: Array<Record<string, unknown>>) => Promise<{ added: number; skipped: number }>;
  exportSelected: (ids?: string[]) => Promise<Account[]>;
}

export const useAccountStore = create<AccountStore>((set, get) => ({
  accounts: [],
  stats: null,
  selectedIds: new Set(),
  page: 1,
  pageSize: 50,
  total: 0,
  totalPages: 1,
  loading: false,
  statusFilter: "",
  search: "",
  sort: "import_desc",

  loadAccounts: async (params = {}) => {
    set({ loading: true });
    try {
      const data = await api.listAccounts({
        page: params.page ?? get().page,
        page_size: params.page_size ?? get().pageSize,
        status: params.status ?? get().statusFilter,
        search: params.search ?? get().search,
        sort: params.sort ?? get().sort,
      });
      set({
        accounts: data.items,
        total: data.total,
        page: data.page,
        pageSize: data.page_size,
        totalPages: data.total_pages,
      });
    } finally {
      set({ loading: false });
    }
  },

  loadStats: async () => {
    const stats = await api.getAccountStats();
    set({ stats });
  },

  setSelected: (ids) => set({ selectedIds: new Set(ids) }),
  toggleSelect: (id) => {
    const next = new Set(get().selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    set({ selectedIds: next });
  },
  selectAll: () => set({ selectedIds: new Set(get().accounts.map((a) => a.id)) }),
  clearSelection: () => set({ selectedIds: new Set() }),

  batchDelete: async () => {
    const result = await api.batchDelete([...get().selectedIds]);
    await get().loadAccounts();
    set({ selectedIds: new Set() });
    return result;
  },

  batchRefresh: async () => {
    const result = await api.batchRefreshTokens([...get().selectedIds]);
    await get().loadAccounts();
    return result;
  },

  batchRefreshQuota: async () => {
    const result = await api.batchRefreshQuota([...get().selectedIds]);
    await get().loadAccounts();
    await get().loadStats();
    return result;
  },

  refreshToken: async (id) => {
    const result = await api.refreshToken(id);
    await get().loadAccounts();
    return result;
  },

  refreshQuota: async (id) => {
    const result = await api.refreshQuota(id);
    await get().loadAccounts();
    await get().loadStats();
    return result;
  },

  renewExpiring: async () => {
    const result = await api.renewExpiring();
    await get().loadAccounts();
    return result;
  },

  importAccounts: async (accounts) => {
    const result = await api.importAccounts(accounts);
    await get().loadAccounts();
    return result;
  },

  exportSelected: async (ids?: string[]) => {
    const result = await api.exportAccounts(ids ?? [...get().selectedIds]);
    return result.accounts;
  },
}));
