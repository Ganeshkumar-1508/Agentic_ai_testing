import { create } from "zustand";
import { api } from "@/lib/api/api-client";

export interface ProviderConfig {
  provider: string;
  api_key?: string;
  base_url?: string;
  model: string;
  enabled: boolean;
  configured?: boolean;
  has_key?: boolean;
  options?: Record<string, unknown>;
}

interface ProviderStore {
  providers: ProviderConfig[];
  activeProvider: ProviderConfig | null;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  lastFetched: number;

  loadProviders: () => Promise<void>;
  saveProviders: (providers: ProviderConfig[]) => Promise<boolean>;
  deleteProvider: (name: string) => Promise<void>;
  testConnection: (provider: ProviderConfig) => Promise<{ status: string; models: string[] }>;
  getActiveProvider: () => ProviderConfig | null;
  isConfigured: () => boolean;
}

const CACHE_TTL = 30_000; // 30 seconds

export const useProviderStore = create<ProviderStore>((set, get) => ({
  providers: [],
  activeProvider: null,
  isLoading: false,
  isSaving: false,
  error: null,
  lastFetched: 0,

  loadProviders: async () => {
    // Skip if recently fetched
    if (Date.now() - get().lastFetched < CACHE_TTL && get().providers.length > 0) return;

    set({ isLoading: true, error: null });
    try {
      const raw = await api.get<any[]>("/api/settings/providers");
      const list = Array.isArray(raw) ? raw : [];
      const providers = list.map((p: any) => ({
        ...p,
        api_key: p.api_key || "",
        enabled: p.enabled ?? true,
        options: p.options || {},
      }));
      const active = providers.find((p) => p.enabled && p.has_key) || null;
      set({ providers, activeProvider: active, lastFetched: Date.now() });
    } catch (e: any) {
      set({ error: e?.message || "Failed to load providers" });
    } finally {
      set({ isLoading: false });
    }
  },

  saveProviders: async (providers) => {
    set({ isSaving: true, error: null });
    try {
      await api.post("/api/settings/providers", providers.map((p) => ({
        provider: p.provider,
        api_key: p.api_key || "",
        base_url: p.base_url || "",
        model: p.model || "",
        enabled: p.enabled,
        options: p.options || {},
      })));
      // Reload from backend to get canonical state
      await get().loadProviders();
      return true;
    } catch (e: any) {
      set({ error: e?.message || "Failed to save" });
      return false;
    } finally {
      set({ isSaving: false });
    }
  },

  deleteProvider: async (name) => {
    try {
      await api.delete(`/api/settings/providers/${name}`);
      await get().loadProviders();
    } catch {}
  },

  testConnection: async (provider) => {
    try {
      const r = await api.post<any>("/api/settings/providers/test-connection", {
        provider: provider.provider,
        api_key: provider.api_key || "",
        base_url: provider.base_url || "",
        model: provider.model || "",
        enabled: provider.enabled,
      });
      return { status: r?.status || "error", models: r?.available_models || [] };
    } catch {
      return { status: "error", models: [] };
    }
  },

  getActiveProvider: () => {
    const { activeProvider, providers } = get();
    if (activeProvider) return activeProvider;
    return providers.find((p) => p.enabled && p.has_key) || null;
  },

  isConfigured: () => {
    const { providers } = get();
    return providers.some((p) => p.enabled && p.has_key && p.model);
  },
}));
