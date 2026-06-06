import { create } from "zustand";
import type { RegisterConfig } from "../types";
import { api } from "../api";

interface RegisterStore {
  config: RegisterConfig | null;
  loading: boolean;
  saving: boolean;

  load: () => Promise<void>;
  save: () => Promise<void>;
  update: (updates: Record<string, unknown>) => void;
  toggle: () => Promise<void>;
  reset: () => Promise<void>;
  setFromSSE: (config: RegisterConfig) => void;
}

export const useRegisterStore = create<RegisterStore>((set, get) => ({
  config: null,
  loading: false,
  saving: false,

  load: async () => {
    set({ loading: true });
    try {
      const config = await api.getRegisterConfig();
      set({ config });
    } finally {
      set({ loading: false });
    }
  },

  save: async () => {
    const cfg = get().config;
    if (!cfg) return;
    set({ saving: true });
    try {
      const updated = await api.updateRegisterConfig({
        mail: cfg.mail,
        proxy: cfg.proxy,
        total: cfg.total,
        threads: cfg.threads,
        mode: cfg.mode,
        target_quota: cfg.target_quota,
        target_available: cfg.target_available,
        check_interval: cfg.check_interval,
        fixed_password: cfg.fixed_password,
        max_node_otp_timeouts: cfg.max_node_otp_timeouts,
        max_node_token_failures: cfg.max_node_token_failures,
        auto_disable_failed_nodes: cfg.auto_disable_failed_nodes,
      });
      set({ config: updated });
    } finally {
      set({ saving: false });
    }
  },

  update: (updates) => {
    const cfg = get().config;
    if (!cfg) return;
    set({ config: { ...cfg, ...updates } as RegisterConfig });
  },

  toggle: async () => {
    const cfg = get().config;
    if (!cfg) return;
    set({ saving: true });
    try {
      const result = cfg.enabled ? await api.stopRegister() : await api.startRegister();
      set({ config: result });
    } finally {
      set({ saving: false });
    }
  },

  reset: async () => {
    const result = await api.resetRegister();
    set({ config: result });
  },

  setFromSSE: (config) => {
    set({ config });
  },
}));
