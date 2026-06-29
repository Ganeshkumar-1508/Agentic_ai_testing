"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/api-client";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import { Save, Loader2, Search, Check, X } from "lucide-react";

interface ProviderField {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  default?: string | number;
}

interface SearchProvider {
  name: string;
  display_name: string;
  description: string;
  config_fields: ProviderField[];
  enabled: boolean;
  config: Record<string, string>;
}

export function SearchProvidersSettings() {
  const [providers, setProviders] = useState<SearchProvider[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");

  useEffect(() => { loadProviders(); }, []);

  const loadProviders = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const raw = await api.get<{ providers: SearchProvider[] }>("/api/search/providers");
      const list = raw?.providers ?? [];
      setProviders(list.map((p: any) => ({
        ...p,
        enabled: p.enabled ?? false,
        config: p.config ?? {},
      })));
    } catch {
      setLoadError("Failed to load search providers");
    } finally {
      setIsLoading(false);
    }
  };

  const toggleProvider = (name: string, enabled: boolean) => {
    setProviders((prev) => prev.map((p) => (p.name === name ? { ...p, enabled } : p)));
    setSaveStatus("idle");
  };

  const updateConfig = (name: string, key: string, value: string) => {
    setProviders((prev) => prev.map((p) =>
      p.name === name ? { ...p, config: { ...p.config, [key]: value } } : p,
    ));
    setSaveStatus("idle");
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await api.post("/api/search/providers", providers.map((p) => ({
        provider: p.name,
        enabled: p.enabled,
        config: { ...p.config, api_key: p.config.api_key || undefined },
      })));
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } catch {
      setSaveStatus("error");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        <SkeletonBlock className="h-16 w-full rounded-3xl" />
        <SkeletonBlock className="h-16 w-full rounded-3xl" />
      </div>
    );
  }

  if (loadError) {
    return <ErrorState message={loadError} onRetry={loadProviders} />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Search Providers</h3>
          <p className="text-xs text-zinc-500 mt-0.5">Configure web search backends for the agent</p>
        </div>
        <Button onClick={handleSave} disabled={isSaving}
          className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1.5">
          {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" strokeWidth={1.5} />}
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </div>

      <AnimatePresence mode="popLayout">
        {providers.map((provider, i) => (
          <motion.div key={provider.name} layout
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 100, damping: 20, delay: i * 0.04 }}
            className="border border-zinc-800/30 rounded-3xl shimmer-bg p-4 space-y-3">

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0">
                  <Search className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                </div>
                <div>
                  <h3 className="text-sm font-medium text-zinc-200">{provider.display_name}</h3>
                  <p className="text-[11px] text-zinc-500">{provider.description}</p>
                </div>
              </div>
              <Switch checked={provider.enabled}
                onCheckedChange={(v) => toggleProvider(provider.name, v)} />
            </div>

            {provider.enabled && provider.config_fields.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                {provider.config_fields.map((field) => (
                  <div key={field.key} className="space-y-1">
                    <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">
                      {field.label}
                    </label>
                    {field.type === "password" ? (
                      <Input type="password"
                        value={provider.config[field.key] || ""}
                        onChange={(e) => updateConfig(provider.name, field.key, e.target.value)}
                        placeholder={field.required ? "Required" : "Optional"}
                        className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg" />
                    ) : (
                      <Input type={field.type || "text"}
                        value={provider.config[field.key] || field.default?.toString() || ""}
                        onChange={(e) => updateConfig(provider.name, field.key, e.target.value)}
                        className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg font-mono" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>

      {saveStatus === "saved" && (
        <div className="flex items-center gap-2 text-emerald-400 text-xs px-1"><Check className="w-3.5 h-3.5" />Saved</div>
      )}
      {saveStatus === "error" && (
        <div className="flex items-center gap-2 text-red-400 text-xs px-1"><X className="w-3.5 h-3.5" />Failed to save</div>
      )}
    </div>
  );
}
