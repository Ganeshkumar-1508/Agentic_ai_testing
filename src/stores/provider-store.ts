import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
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
  available_models?: string[];
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

const CACHE_TTL = 30_000;

export const useProviderStore = create<ProviderStore>()(
  persist(
    (set, get) => ({
      providers: [],
      activeProvider: null,
      isLoading: false,
      isSaving: false,
      error: null,
      lastFetched: 0,

      loadProviders: async () => {
        // Always fetch fresh data — no cache
        set({ isLoading: true, error: null });
        try {
          const raw = await api.get<any[]>("/api/settings/providers");
          const list = Array.isArray(raw) ? raw : [];
          const providers = list.map((p: any) => ({ ...p, api_key: p.api_key || "", enabled: p.enabled ?? true, options: p.options || {} }));
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
            provider: p.provider, api_key: p.api_key || "", base_url: p.base_url || "",
            model: p.model || "", enabled: p.enabled, options: p.options || {},
          })));
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
        try { await api.delete(`/api/settings/providers/${name}`); await get().loadProviders(); }
        catch {}
      },

      testConnection: async (provider) => {
        try {
          const r = await api.post<any>("/api/settings/providers/test-connection", {
            provider: provider.provider, api_key: provider.api_key || "",
            base_url: provider.base_url || "", model: provider.model || "", enabled: provider.enabled,
          });
          const models = r?.available_models || [];
          if (models.length > 0) {
            const updated = get().providers.map(p =>
              p.provider === provider.provider ? { ...p, available_models: models } : p
            );
            set({ providers: updated });
          }
          return { status: r?.status || "error", models };
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
        return get().providers.some((p) => p.enabled && p.has_key && p.model);
      },
    }),
    {
      name: "provider-store",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        providers: state.providers,
        activeProvider: state.activeProvider,
        lastFetched: state.lastFetched,
      }),
    },
  ),
);
