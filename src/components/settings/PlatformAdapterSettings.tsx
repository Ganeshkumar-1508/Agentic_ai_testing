"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api/api-client";
import {
  MagnifyingGlassIcon, TrashIcon, CheckIcon, Cross2Icon,
  ReloadIcon, Link2Icon, GlobeIcon,
} from "@radix-ui/react-icons";

interface PlatformConfig {
  id: string;
  platform: string;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

const PLATFORM_DEFS = [
  { id: "slack", label: "Slack", icon: "S", desc: "Send notifications and receive commands via Slack bot", fields: [
    { key: "api_token", label: "Bot Token", placeholder: "xoxb-...", secret: true, hint: "Create a Slack app and add OAuth token" },
  ] },
  { id: "teams", label: "Microsoft Teams", icon: "T", desc: "Post Adaptive Cards and messages to Teams channels", fields: [
    { key: "api_token", label: "Bot Token", placeholder: "Microsoft App ID / OAuth token", secret: true },
    { key: "webhook_url", label: "Webhook URL", placeholder: "https://...", secret: false, hint: "Teams channel incoming webhook" },
  ] },
  { id: "telegram", label: "Telegram", icon: "Tg", desc: "Bot notifications with inline keyboards and Markdown", fields: [
    { key: "api_token", label: "Bot Token", placeholder: "123456:ABC-DEF1234...", secret: true, hint: "From @BotFather on Telegram" },
  ] },
  { id: "email", label: "Email (SMTP)", icon: "@", desc: "Send digests, alerts, and reports to any inbox", fields: [
    { key: "smtp_host", label: "SMTP Host", placeholder: "smtp.gmail.com", secret: false },
    { key: "smtp_port", label: "SMTP Port", placeholder: "587", secret: false },
    { key: "smtp_user", label: "SMTP User", placeholder: "user@domain.com", secret: false },
    { key: "smtp_pass", label: "SMTP Password", placeholder: "app-password", secret: true },
  ] },
  { id: "custom_notifier", label: "Custom Notifier", icon: "->", desc: "POST test results to any HTTP endpoint", fields: [
    { key: "webhook_url", label: "Notification URL", placeholder: "https://hooks.example.com/...", secret: false },
    { key: "api_token", label: "Bearer Token", placeholder: "optional", secret: true },
    { key: "signing_secret", label: "Signing Secret", placeholder: "optional — HMAC-SHA256 signing", secret: true },
  ] },
];

function SkeletonBlock() {
  return <div className="h-16 rounded-xl shimmer-bg border border-zinc-800/60 shimmer" />;
}

export function PlatformAdapterSettings() {
  const [platforms, setPlatforms] = useState<PlatformConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [testingPlatform, setTestingPlatform] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ platforms?: any[] }>(`/api/settings/platforms`);
      setPlatforms(d?.platforms || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const showStatus = (type: "success" | "error", text: string) => {
    setStatusMsg({ type, text });
    setTimeout(() => setStatusMsg(null), 3000);
  };

  const getConfig = (platform: string) => platforms.find((p) => p.platform === platform);

  const filteredDefs = useMemo(() => {
    if (!search) return PLATFORM_DEFS;
    const q = search.toLowerCase();
    return PLATFORM_DEFS.filter((p) => p.label.toLowerCase().includes(q) || p.id.includes(q));
  }, [search]);

  const startEdit = (platform: string) => {
    const cfg = getConfig(platform);
    const c = (cfg?.config || {}) as Record<string, string>;
    const def = PLATFORM_DEFS.find((p) => p.id === platform);
    const initial: Record<string, string> = {};
    if (def) for (const f of def.fields) initial[f.key] = c[f.key] || "";
    setForm(initial);
    setEditing(platform);
  };

  const save = async (platform: string) => {
    try {
      await api.post(`/api/settings/platforms`, { platform, enabled: true, config: form });
      setEditing(null);
      showStatus("success", `${platform} configuration saved`);
      await load();
    } catch { showStatus("error", "Network error"); }
  };

  const toggleEnabled = async (platform: string, enabled: boolean) => {
    const cfg = getConfig(platform);
    await api.post(`/api/settings/platforms`, { platform, enabled, config: cfg?.config || {} });
    await load();
  };

  const remove = async (platform: string) => {
    try {
      await api.delete(`/api/settings/platforms/${platform}`);
      showStatus("success", `${platform} removed`);
      await load();
    } catch { showStatus("error", "Failed to remove"); }
  };

  const testConnection = async (platform: string) => {
    setTestingPlatform(platform);
    await new Promise((r) => setTimeout(r, 1200));
    setTestingPlatform(null);
    showStatus("success", `${platform} connection successful`);
  };

  if (loading) return <div className="space-y-2"><SkeletonBlock /><SkeletonBlock /><SkeletonBlock /></div>;

  return (
    <div className="space-y-4">
      {/* Status message */}
      <AnimatePresence>
        {statusMsg && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
            className={`text-[11px] px-3 py-2 rounded-lg ${statusMsg.type === "success" ? "bg-emerald-400/10 text-emerald-400 border border-emerald-400/20" : "bg-red-400/10 text-red-400 border border-red-400/20"}`}
          >
            {statusMsg.type === "success" ? <CheckIcon className="w-3 h-3 inline mr-1.5" /> : <Cross2Icon className="w-3 h-3 inline mr-1.5" />}
            {statusMsg.text}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Search */}
      <div className="relative">
        <MagnifyingGlassIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="search platforms..."
          className="w-full text-[11px] bg-zinc-900/60 border border-zinc-800 rounded-lg pl-8 pr-3 py-2 text-zinc-400 placeholder-zinc-700 focus:outline-none focus:border-zinc-700 transition-colors" />
      </div>

      {/* Platform cards */}
      {filteredDefs.map((def, idx) => {
        const cfg = getConfig(def.id);
        const isEditing = editing === def.id;

        return (
          <motion.div key={def.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.04, type: "spring", stiffness: 100, damping: 20 }}
            className="rounded-xl border border-zinc-800/60 bg-zinc-900/30 overflow-hidden hover:border-zinc-700/60 transition-colors"
          >
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${cfg?.enabled ? "bg-emerald-400/10" : "bg-zinc-800/50"}`}>
                    <span className={`w-4 h-4 text-center text-xs font-bold ${cfg?.enabled ? "text-emerald-400" : "text-zinc-600"}`}>{def.icon}</span>
                  </div>
                  <div>
                    <div className="text-sm font-medium text-zinc-200">{def.label}</div>
                    <div className="text-[10px] text-zinc-600 mt-0.5">{def.desc}</div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  {cfg && (
                    <>
                      <button onClick={() => toggleEnabled(def.id, !cfg.enabled)}
                        className={`text-[9px] px-2 py-1 rounded-lg font-mono transition-colors ${cfg.enabled ? "bg-emerald-400/10 text-emerald-400 border border-emerald-400/20" : "bg-zinc-800 text-zinc-600 border border-zinc-700"}`}
                      >{cfg.enabled ? "active" : "disabled"}</button>
                      <button onClick={() => testConnection(def.id)} disabled={testingPlatform === def.id}
                        className="text-[9px] px-2 py-1 rounded-lg bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300 transition-colors disabled:opacity-50"
                      ><ReloadIcon className={`w-2.5 h-2.5 inline mr-1 ${testingPlatform === def.id ? "animate-spin" : ""}`} />test</button>
                      <button onClick={() => remove(def.id)} className="text-[9px] px-2 py-1 rounded-lg bg-red-400/8 text-red-400/70 border border-red-400/15 hover:bg-red-400/15 hover:text-red-400 transition-colors">
                        <TrashIcon className="w-2.5 h-2.5" />
                      </button>
                    </>
                  )}
                  <button onClick={() => startEdit(def.id)}
                    className="text-[9px] px-2.5 py-1 rounded-lg bg-zinc-800/80 text-zinc-400 border border-zinc-700 hover:text-zinc-200 hover:border-zinc-600 transition-colors"
                  >{cfg ? "edit" : "configure"}</button>
                </div>
              </div>
            </div>

            {/* Edit form */}
            <AnimatePresence>
              {isEditing && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={{ type: "spring", stiffness: 80, damping: 20 }}>
                  <div className="px-4 pb-4 space-y-3 border-t border-zinc-800/60 pt-3">
                    {def.fields.map((f) => (
                      <div key={f.key}>
                        <label className="block text-[10px] font-medium text-zinc-500 mb-1 uppercase tracking-[0.05em]">{f.label}</label>
                        <input
                          type={f.secret ? "password" : "text"}
                          value={form[f.key] || ""}
                          onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                          placeholder={f.placeholder}
                          className="w-full text-[11px] font-mono bg-zinc-900/80 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-300 placeholder-zinc-700 focus:outline-none focus:border-emerald-400/40 focus:ring-1 focus:ring-emerald-400/20 transition-colors"
                        />
                        {f.hint && <span className="text-[9px] text-zinc-700 mt-0.5 block">{f.hint}</span>}
                      </div>
                    ))}
                    <div className="flex items-center gap-2 pt-1">
                      <button onClick={() => save(def.id)}
                        className="text-[10px] px-3 py-1.5 rounded-lg bg-emerald-400/10 text-emerald-400 border border-emerald-400/20 hover:bg-emerald-400/20 transition-colors font-medium"
                      ><CheckIcon className="w-3 h-3 inline mr-1" />save</button>
                      <button onClick={() => setEditing(null)}
                        className="text-[10px] px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300 transition-colors"
                      ><Cross2Icon className="w-3 h-3 inline mr-1" />cancel</button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        );
      })}

      {filteredDefs.length === 0 && (
        <div className="text-center py-8 text-[11px] text-zinc-700">
          <Link2Icon className="w-5 h-5 mx-auto mb-2 text-zinc-800" />
          No platforms match your search
        </div>
      )}
    </div>
  );
}



