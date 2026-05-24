import { create } from "zustand";
import type { AppConfig, TokenRefreshConfig } from "../types";
import { api } from "../api";

interface SettingsStore {
  config: AppConfig | null;
  loading: boolean;

  load: () => Promise<void>;
  save: (updates: Record<string, unknown>) => Promise<void>;
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  config: null,
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const config = await api.getSettings();
      set({ config });
    } finally {
      set({ loading: false });
    }
  },

  save: async (updates) => {
    const config = await api.updateSettings(updates);
    set({ config });
  },
}));
