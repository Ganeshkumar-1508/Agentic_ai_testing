"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StyledSelect } from "@/components/ui/styled-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import {
  Eye, EyeOff, Check, X, Loader2, Server, Plug, Wifi, WifiOff,
  Save, Plus, Trash2, Info, Brain,
  Sliders,
} from "lucide-react";
import { useProviderStore, type ProviderConfig } from "@/stores/provider-store";

function Tooltip({ text, className }: { text: string; className?: string }) {
  return (
    <span className={cn("group relative inline-flex cursor-help", className)}>
      <Info size={11} strokeWidth={1.5} className="text-zinc-600 hover:text-zinc-400 transition-colors" />
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded-lg bg-zinc-800 border border-zinc-700 text-[9px] text-zinc-300 whitespace-normal w-52 text-center opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-10 shadow-lg">
        {text}
      </span>
    </span>
  );
}

function SliderInput({ value, min, max, step, onChange, label }: {
  value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; label: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-[9px] text-zinc-600 font-mono tabular-nums">{label}</span>
        <span className="text-[10px] text-zinc-400 font-mono tabular-nums">{value.toFixed(step < 0.1 ? 2 : 1)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 bg-zinc-800 rounded-full appearance-none cursor-pointer accent-emerald-400 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-emerald-400 [&::-webkit-slider-thumb]:shadow-[0_0_4px_rgba(52,211,153,0.3)]" />
    </div>
  );
}

function TagInput({ values, onChange, placeholder }: {
  values: string[]; onChange: (v: string[]) => void; placeholder?: string;
}) {
  const [val, setVal] = useState("");
  const add = () => {
    if (!val.trim()) return;
    onChange([...values, val.trim()]);
    setVal("");
  };
  return (
    <div className="space-y-1">
      <div className="flex gap-1">
        <input type="text" value={val} onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder || "Add..."}
          className="flex-1 bg-zinc-900/80 border border-zinc-800 rounded-lg px-2 py-1 text-[10px] font-mono text-zinc-300 placeholder:text-zinc-600 outline-none focus:border-emerald-500/40" />
        <button type="button" onClick={add} disabled={!val.trim()}
          className="px-1.5 rounded-lg text-[9px] bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors disabled:opacity-30 active:scale-[0.95]">Add</button>
      </div>
      <div className="flex flex-wrap gap-1">
        {values.map((v, i) => (
          <span key={i} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-zinc-800/60 border border-zinc-700/30 text-[9px] font-mono text-zinc-400">
            {v}
            <button type="button" onClick={() => onChange(values.filter((_, j) => j !== i))}
              className="text-zinc-600 hover:text-zinc-400">
              <X size={8} strokeWidth={2} />
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}

function CollapsibleSection({ title, icon: Icon, defaultOpen = false, children }: {
  title: string; icon: any; defaultOpen?: boolean; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-zinc-800/30 rounded-xl overflow-hidden">
      <button type="button" onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-3 py-2 text-[10px] font-medium text-zinc-500 hover:text-zinc-300 bg-zinc-900/30 transition-colors">
        <Icon size={11} strokeWidth={1.5} />
        <span className="uppercase tracking-wider">{title}</span>
        <span className="ml-auto">
          {open ? (
            <svg className="w-2.5 h-2.5 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" /></svg>
          ) : (
            <svg className="w-2.5 h-2.5 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" /></svg>
          )}
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }} className="overflow-hidden">
            <div className="px-3 py-2.5 space-y-2.5 bg-zinc-900/20">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function BackendProvidersSettings() {
  const {
    providers, isLoading, isSaving, error,
    loadProviders, saveProviders, deleteProvider, testConnection,
  } = useProviderStore();

  const [localProviders, setLocalProviders] = useState<ProviderConfig[]>([]);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [connectionStatuses, setConnectionStatuses] = useState<Record<string, string>>({});
  const [connectionErrors, setConnectionErrors] = useState<Record<string, string>>({});
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProvider, setNewProvider] = useState("");

  // Load on mount
  useEffect(() => { loadProviders(); }, [loadProviders]);

  // Auto-fetch models when API key + base URL are both filled
  const autoFetchTimerRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  useEffect(() => {
    localProviders.forEach((p) => {
      if (p.api_key && p.base_url && !availableModels[p.provider]?.length && !(p as any).available_models?.length) {
        clearTimeout(autoFetchTimerRef.current[p.provider]);
        autoFetchTimerRef.current[p.provider] = setTimeout(() => {
          testConnection(p).then((result) => {
            if (result.models.length > 0) {
              setAvailableModels((prev) => ({ ...prev, [p.provider]: result.models }));
            }
          });
        }, 1500);
      }
    });
    return () => Object.values(autoFetchTimerRef.current).forEach(clearTimeout);
  }, [localProviders.map(p => `${p.api_key}-${p.base_url}`).join(',')]);

  // Sync global store to local state for editing
  useEffect(() => {
    setLocalProviders(providers.map((p) => ({ ...p })));
  }, [providers]);

  const updateLocal = (provider: string, field: string, value: any) => {
    setLocalProviders((prev) => prev.map((p) => (p.provider === provider ? { ...p, [field]: value } : p)));
    setSaveStatus("idle");
  };

  const updateOpt = (provider: string, path: string, value: any) => {
    setLocalProviders((prev) => prev.map((p) => {
      if (p.provider !== provider) return p;
      const opts: any = { ...(p.options || {}) };
      if (path === "thinking.enabled") opts.thinking = { ...(opts.thinking || {}), enabled: value };
      else if (path === "thinking.effort") opts.thinking = { ...(opts.thinking || {}), effort: value };
      else if (path === "thinking.budget_tokens") opts.thinking = { ...(opts.thinking || {}), budget_tokens: value };
      else opts[path] = value;
      return { ...p, options: opts };
    }));
    setSaveStatus("idle");
  };

  const addProvider = () => {
    const name = newProvider.trim().toLowerCase().replace(/\s+/g, "_");
    if (!name || localProviders.find((p) => p.provider === name)) return;
    setLocalProviders((prev) => [...prev, { provider: name, api_key: "", base_url: "", model: "", enabled: true, configured: false, has_key: false, options: {} }]);
    setNewProvider("");
    setShowAddForm(false);
    setSaveStatus("idle");
  };

  const removeProvider = (name: string) => {
    setLocalProviders((prev) => prev.filter((p) => p.provider !== name));
    setSaveStatus("idle");
  };

  const handleSave = async () => {
    const ok = await saveProviders(localProviders);
    if (ok) {
      setSaveStatus("saved");
      const active = localProviders.filter(p => p.enabled && p.has_key);
      if (active.length > 0) {
        toast.success(`Connected! ${active.map(p => p.provider).join(", ")} — API key saved and ready for Chat, Agent, Pipeline`);
      } else {
        toast.success("Provider saved");
      }
    } else {
      setSaveStatus("error");
    }
  };

  const handleTest = async (provider: ProviderConfig) => {
    setConnectionStatuses((prev) => ({ ...prev, [provider.provider]: "testing" }));
    setConnectionErrors((prev) => ({ ...prev, [provider.provider]: "" }));
    const result = await testConnection(provider);
    setConnectionStatuses((prev) => ({ ...prev, [provider.provider]: result.status }));
    if (result.status !== "ok") setConnectionErrors((prev) => ({ ...prev, [provider.provider]: "Connection failed" }));
    if (result.models.length > 0) setAvailableModels((prev) => ({ ...prev, [provider.provider]: result.models }));
    setTimeout(() => { setConnectionStatuses((prev) => ({ ...prev, [provider.provider]: "idle" })); }, 4000);
  };

  if (isLoading && localProviders.length === 0) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <SkeletonBlock key={i} className="h-20 w-full rounded-3xl" />
        ))}
      </div>
    );
  }

  if (error && localProviders.length === 0) {
    return <ErrorState message={error} onRetry={loadProviders} />;
  }

  return (
    <div className="space-y-4">
      <AnimatePresence mode="popLayout">
        {localProviders.length === 0 && !showAddForm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-12 border border-dashed border-zinc-800/50 rounded-3xl bg-zinc-900/30">
            <Server className="w-8 h-8 text-zinc-600 mb-3" strokeWidth={1.2} />
            <p className="text-sm text-zinc-500 mb-1">No providers configured</p>
            <p className="text-xs text-zinc-600 mb-4">Add an LLM provider to get started</p>
            <Button onClick={() => setShowAddForm(true)}
              className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1.5">
              <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />Add Provider</Button>
          </motion.div>
        )}

        {localProviders.map((provider, i) => {
          const opts = provider.options || {};
          const thinkingEnabled = (opts as any).thinking?.enabled !== false;
          const thinkingEffort = (opts as any).thinking?.effort || "medium";
          const budgetTokens = (opts as any).thinking?.budget_tokens || 4096;

          return (
            <motion.div key={provider.provider} layout
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ type: "spring", stiffness: 100, damping: 20, delay: i * 0.04 }}
              className="border border-zinc-800/30 rounded-3xl shimmer-bg p-4 space-y-3">

              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0">
                    <Server className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-zinc-200 capitalize">{provider.provider}</h3>
                    {provider.base_url && (
                      <p className="text-[11px] text-zinc-600 font-mono truncate max-w-[200px]">{provider.base_url}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <motion.button whileTap={{ scale: 0.92 }}
                    onClick={() => handleTest(provider)}
                    disabled={connectionStatuses[provider.provider] === "testing"}
                    className="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40 transition-colors">
                    {connectionStatuses[provider.provider] === "testing" ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                    ) : connectionStatuses[provider.provider] === "ok" ? (
                      <Wifi className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
                    ) : connectionStatuses[provider.provider] === "error" ? (
                      <WifiOff className="w-3.5 h-3.5 text-red-400" strokeWidth={1.5} />
                    ) : (
                      <Plug className="w-3.5 h-3.5" strokeWidth={1.5} />
                    )}
                  </motion.button>
                  <button type="button" onClick={() => removeProvider(provider.provider)}
                    className="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-red-500/5 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </button>
                  <Switch checked={provider.enabled}
                    onCheckedChange={(v) => { setLocalProviders((prev) => prev.map((p) => ({ ...p, enabled: p.provider === provider.provider ? v : false }))); setSaveStatus("idle"); }} />
                </div>
              </div>

              {/* Error */}
              <AnimatePresence>
                {connectionStatuses[provider.provider] === "error" && connectionErrors[provider.provider] && (
                  <motion.p initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    className="text-[11px] text-red-400 overflow-hidden">
                    {connectionErrors[provider.provider]}
                  </motion.p>
                )}
              </AnimatePresence>

              {/* Basic fields */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                <div className="space-y-1">
                  <label className="flex items-center gap-1 text-[10px] text-zinc-500 uppercase tracking-wider font-medium">
                    API Key
                    <Tooltip text="Stored securely — never exposed in UI" />
                  </label>
                  <div className="relative">
                    <Input type={showKeys[provider.provider] ? "text" : "password"}
                      value={provider.api_key || ""}
                      onChange={(e) => updateLocal(provider.provider, "api_key", e.target.value)}
                      placeholder="sk-..." className="bg-zinc-900/80 border-zinc-800 text-xs pr-8 h-8 rounded-lg focus:border-emerald-500/40" />
                    <button type="button" tabIndex={-1}
                      onClick={() => setShowKeys((prev) => ({ ...prev, [provider.provider]: !prev[provider.provider] }))}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300">
                      {showKeys[provider.provider] ? <EyeOff className="w-3 h-3" strokeWidth={1.5} /> : <Eye className="w-3 h-3" strokeWidth={1.5} />}
                    </button>
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="flex items-center gap-1 text-[10px] text-zinc-500 uppercase tracking-wider font-medium">
                    Base URL
                    <Tooltip text="API endpoint URL" />
                  </label>
                  <Input value={provider.base_url || ""}
                    onChange={(e) => updateLocal(provider.provider, "base_url", e.target.value)}
                    placeholder="https://api.example.com/v1"
                    className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg font-mono focus:border-emerald-500/40" />
                </div>
                <div className="space-y-1">
                  <label className="flex items-center gap-1 text-[10px] text-zinc-500 uppercase tracking-wider font-medium">
                    Model
                    <Tooltip text="Enter base URL and API key, click Test Connection to fetch available models" />
                  </label>
                  {(availableModels[provider.provider]?.length > 0 || (provider as any).available_models?.length > 0) ? (
                    <StyledSelect value={provider.model}
                      onChange={(e) => updateLocal(provider.provider, "model", e.target.value)}>
                      <option value="" className="bg-surface text-zinc-300">Select a model...</option>
                      {(availableModels[provider.provider] || (provider as any).available_models || []).map((m: string) => (
                        <option key={m} value={m} className="bg-surface text-zinc-300">{m}</option>
                      ))}
                    </StyledSelect>
                  ) : (
                    <Input value={provider.model}
                      onChange={(e) => updateLocal(provider.provider, "model", e.target.value)}
                      placeholder="Enter base URL + API key, click Test Connection"
                      className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg font-mono focus:border-emerald-500/40" />
                  )}
                </div>
              </div>

              {/* Thinking */}
              <CollapsibleSection title="Thinking / Reasoning" icon={Brain}>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-zinc-400">Enabled</span>
                  <Switch checked={thinkingEnabled}
                    onCheckedChange={(v) => updateOpt(provider.provider, "thinking.enabled", v)} />
                </div>
                {thinkingEnabled && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                    <div className="space-y-1">
                      <label className="text-[9px] text-zinc-600 uppercase tracking-wider font-medium">Effort</label>
                      <select value={thinkingEffort}
                        onChange={(e) => updateOpt(provider.provider, "thinking.effort", e.target.value)}
                        className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-2 py-1 text-[10px] text-zinc-300 outline-none focus:border-emerald-500/40">
                        {["low", "medium", "high", "max"].map((e) => (
                          <option key={e} value={e} className="bg-zinc-900">{e}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] text-zinc-600 uppercase tracking-wider font-medium">Budget Tokens</label>
                      <input type="number" value={budgetTokens} min={1024} max={64000} step={1024}
                        onChange={(e) => updateOpt(provider.provider, "thinking.budget_tokens", parseInt(e.target.value) || 4096)}
                        className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-2 py-1 text-[10px] font-mono text-zinc-300 outline-none focus:border-emerald-500/40" />
                    </div>
                  </div>
                )}
              </CollapsibleSection>

              {/* Advanced */}
              <CollapsibleSection title="Advanced Parameters" icon={Sliders}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <SliderInput value={(opts as any).temperature ?? 1} min={0} max={2} step={0.1}
                    onChange={(v) => updateOpt(provider.provider, "temperature", v)} label="Temperature" />
                  <SliderInput value={(opts as any).top_p ?? 1} min={0} max={1} step={0.05}
                    onChange={(v) => updateOpt(provider.provider, "top_p", v)} label="Top P" />
                  <div className="space-y-1">
                    <label className="text-[9px] text-zinc-600 uppercase tracking-wider font-medium">Max Tokens</label>
                    <input type="number" value={(opts as any).max_tokens ?? ""} min={1} max={131072}
                      onChange={(e) => updateOpt(provider.provider, "max_tokens", e.target.value ? parseInt(e.target.value) : undefined)}
                      placeholder="4096" className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-2 py-1 text-[10px] font-mono text-zinc-300 outline-none focus:border-emerald-500/40" />
                  </div>
                </div>
                <div className="space-y-1 pt-1">
                  <label className="text-[9px] text-zinc-600 uppercase tracking-wider font-medium">Stop Sequences</label>
                  <TagInput values={(opts as any).stop || []} onChange={(v) => updateOpt(provider.provider, "stop", v)} placeholder="Add stop sequence..." />
                </div>
              </CollapsibleSection>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Add form */}
      <AnimatePresence>
        {showAddForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden">
            <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl p-4">
              <div className="flex items-end gap-3">
                <div className="flex-1 space-y-1">
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Provider Name</label>
                  <Input value={newProvider} onChange={(e) => setNewProvider(e.target.value)}
                    placeholder="e.g. openai, anthropic, nvidia, opencode"
                    className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg focus:border-emerald-500/40"
                    onKeyDown={(e) => e.key === "Enter" && addProvider()} />
                </div>
                <Button onClick={addProvider} disabled={!newProvider.trim()}
                  className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold">Add</Button>
                <Button onClick={() => { setShowAddForm(false); setNewProvider(""); }} variant="outline"
                  className="h-8 px-3 rounded-lg text-xs border-zinc-800">Cancel</Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!showAddForm && localProviders.length > 0 && (
        <Button onClick={() => setShowAddForm(true)} variant="outline"
          className="w-full h-10 border-dashed border-zinc-800/50 rounded-3xl text-xs text-zinc-500 gap-1.5 hover:text-zinc-300 transition-colors">
          <Plus className="w-4 h-4" strokeWidth={1.5} />Add Provider</Button>
      )}

      {/* Save bar */}
      {localProviders.length > 0 && (
        <motion.div layout className="flex items-center justify-between border border-zinc-800/30 rounded-3xl shimmer-bg px-5 py-3">
          {saveStatus === "saved" ? (
            <div className="flex items-center gap-2 text-emerald-400 text-xs"><Check className="w-4 h-4" strokeWidth={2} />Saved — provider active across all components</div>
          ) : saveStatus === "error" ? (
            <div className="flex items-center gap-2 text-red-400 text-xs"><X className="w-4 h-4" strokeWidth={2} />Failed to save</div>
          ) : (
            <span className="text-xs text-zinc-500">{localProviders.filter((p) => p.enabled).length} enabled</span>
          )}
          <Button onClick={handleSave} disabled={isSaving}
            className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1.5 active:scale-[0.97]">
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} /> : <Save className="w-3.5 h-3.5" strokeWidth={1.5} />}
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </motion.div>
      )}
    </div>
  );
}
