"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Globe, Webhook, Terminal, Plus, Check, X, Loader2, AlertCircle, Shield, Eye, UserCheck, Sparkles } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { PlatformAdapterSettings } from "@/components/settings/PlatformAdapterSettings";

const TIER_LABEL: Record<number, string> = { 1: "Autonomous", 2: "Supervised", 3: "Human" };
const TIER_ICONS: Record<number, React.ElementType> = { 1: Shield, 2: Eye, 3: UserCheck };

const channelIcons: Record<string, React.ReactNode> = {
  webhook: <Webhook size={14} strokeWidth={1.5} />,
  cli: <Terminal size={14} strokeWidth={1.5} />,
  default: <Globe size={14} strokeWidth={1.5} />,
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } },
};

export default function ChannelsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState("Webhook");
  const [url, setUrl] = useState("");
  const [prompt, setPrompt] = useState("");
  const [tier, setTier] = useState(2);
  const [creating, setCreating] = useState(false);

  const { data: webhooksData } = useQuery({
    queryKey: ["webhooks"],
    queryFn: async () => {
      const res = await api.get("/api/settings/webhooks");
      return (res as any)?.webhooks ?? [];
    },
  });

  const urlError = url.trim() && !url.match(/^https?:\/\/.+/)
    ? "Must be a valid HTTP or HTTPS URL"
    : null;

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !url.trim() || urlError) return;
    setCreating(true);
    try {
      await api.post("/api/settings/webhooks", {
        name: name.trim(),
        url: url.trim(),
        type: type.toLowerCase(),
        events: ["job:completed"],
        enabled: true,
        prompt: prompt.trim(),
        tier,
        skills: [],
      });
      toast.success("Channel created");
      setName("");
      setType("Webhook");
      setUrl("");
      setPrompt("");
      setTier(2);
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["webhooks"] });
    } catch {
      toast.error("Failed to create channel");
    } finally {
      setCreating(false);
    }
  }, [name, url, type, prompt, tier, urlError, queryClient]);

  const channels = (webhooksData || []).map((w: any) => ({
    name: w.name,
    type: w.type || "webhook",
    connected: w.enabled,
    tools: w.events?.join(", ") || "",
    prompt: w.prompt || "",
    tier: w.tier ?? 2,
  }));

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
        <span className="text-xs font-mono text-zinc-600">/channels</span>
      </div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Channels</h1>
          <p className="text-sm text-zinc-600 mt-1 max-w-[65ch]">Multi-platform delivery channels for agent output</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-all duration-300 active:scale-[0.97]"
        >
          {showForm ? <X size={14} strokeWidth={1.5} /> : <Plus size={14} strokeWidth={1.5} />}
          {showForm ? "Cancel" : "Add Channel"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden mb-8"
          >
            <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-[2rem] p-6 space-y-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
              <div className="grid grid-cols-2 gap-5">
                <div className="space-y-1.5">
                  <label className="text-xs text-zinc-500 font-medium">Channel Name</label>
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. github-pr-reviews"
                    className="w-full bg-zinc-900/80 border border-zinc-800 rounded-xl px-3.5 py-2 text-sm text-zinc-300 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors duration-300" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-zinc-500 font-medium">Type</label>
                  <select value={type} onChange={(e) => setType(e.target.value)}
                    className="w-full bg-zinc-900/80 border border-zinc-800 rounded-xl px-3.5 py-2 text-sm text-zinc-300 outline-none focus:border-emerald-500/40 transition-colors duration-300">
                    <option>Webhook</option>
                    <option>WebSocket</option>
                    <option>Slack</option>
                    <option>Discord</option>
                  </select>
                </div>
                <div className="space-y-1.5 col-span-2">
                  <label className="text-xs text-zinc-500 font-medium">URL / Endpoint</label>
                  <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://hooks.example.com/..."
                    className={cn("w-full bg-zinc-900/80 border rounded-xl px-3.5 py-2 text-sm text-zinc-300 placeholder-zinc-600 font-mono outline-none transition-colors duration-300", url && !urlError ? "border-emerald-500/30" : urlError ? "border-red-500/40" : "border-zinc-800 focus:border-emerald-500/40")} />
                  {urlError && <p className="flex items-center gap-1 text-[10px] text-red-400 mt-1"><AlertCircle size={10} strokeWidth={1.5} />{urlError}</p>}
                </div>
              </div>

              <div className="space-y-3">
                <label className="text-xs text-zinc-500 font-medium">Prompt Template</label>
                <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} placeholder="Review PR #{pull_request.number}: {pull_request.title}&#10;Author: {pull_request.user.login}&#10;Diff: {pull_request.diff_url}"
                  className="w-full bg-zinc-900/80 border border-zinc-800 rounded-xl px-3.5 py-2 text-sm text-zinc-300 placeholder-zinc-600 font-mono outline-none focus:border-emerald-500/40 transition-colors resize-y" />
                <p className="text-[10px] text-zinc-700">Use <code className="text-zinc-500">{'{payload.field}'}</code> to reference webhook payload fields. <code className="text-zinc-500">{'{__raw__}'}</code> dumps the entire payload.</p>
              </div>

              <div className="space-y-3">
                <label className="text-xs text-zinc-500 font-medium">Autonomy Tier</label>
                <div className="flex gap-2">
                  {([1, 2, 3] as const).map((t) => {
                    const TierIcon = TIER_ICONS[t] || Shield;
                    const active = tier === t;
                    return (
                      <button key={t} onClick={() => setTier(t)}
                        className={cn("flex-1 flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs border transition-all active:scale-[0.97]",
                          active ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-zinc-900/60 border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700")}>
                        <TierIcon size={12} strokeWidth={1.5} />
                        {TIER_LABEL[t]}
                      </button>
                    );
                  })}
                </div>
                <p className="text-[10px] text-zinc-700">Tier 1: agent runs autonomously · Tier 2: pauses for review · Tier 3: creates a proposal only</p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-1">
                <button onClick={() => setShowForm(false)} className="px-4 py-2 text-xs rounded-xl text-zinc-500 hover:text-zinc-300 transition-colors active:scale-[0.97]">Cancel</button>
                <button onClick={handleCreate} disabled={creating || !name.trim() || !url.trim() || !!urlError}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-xl bg-emerald-500 text-black font-medium hover:bg-emerald-400 transition-all duration-300 active:scale-[0.97] disabled:opacity-30 disabled:cursor-not-allowed disabled:active:scale-100">
                  {creating ? <Loader2 size={14} strokeWidth={1.5} className="animate-spin" /> : <Check size={14} strokeWidth={1.5} />}
                  {creating ? "Creating..." : "Create Channel"}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="divide-y divide-zinc-800/30 border border-zinc-800/50 rounded-[2rem] overflow-hidden"
      >
        {channels.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-zinc-600 text-sm gap-3">
            <div className="w-12 h-12 rounded-2xl bg-zinc-900/50 border border-zinc-800/30 flex items-center justify-center">
              <Globe size={20} strokeWidth={1} className="text-zinc-500" />
            </div>
            <p>No channels configured</p>
            <p className="text-xs text-zinc-700">Click &quot;Add Channel&quot; to configure a delivery channel</p>
          </div>
        ) : (
          channels.map((ch, i) => (
            <motion.div
              key={ch.name}
              variants={itemVariants}
              className="flex items-center justify-between px-6 py-4 hover:bg-zinc-900/20 transition-colors duration-200"
            >
              <div className="flex items-center gap-3">
                <span className="w-8 h-8 rounded-xl bg-zinc-800/40 flex items-center justify-center text-zinc-500 border border-zinc-800/20">
                  {channelIcons[ch.type] || channelIcons.default}
                </span>
                <div>
                  <p className="text-sm font-medium text-zinc-300">{ch.name}</p>
                  {ch.tools && (
                    <p className="text-xs text-zinc-600 font-mono mt-0.5">{ch.tools}</p>
                  )}
                </div>
              </div>
              <span className={cn(
                "text-[10px] px-2.5 py-0.5 rounded-full font-medium border",
                ch.connected
                  ? "bg-emerald-500/10 text-emerald-400/80 border-emerald-500/20"
                  : "bg-zinc-800/30 text-zinc-500 border-zinc-700/30"
              )}>
                {ch.connected ? "active" : "inactive"}
              </span>
            </motion.div>
          ))
        )}
      </motion.div>

      {/* Platform Adapters (Slack, Teams, Telegram, Email) */}
      <div className="mt-12">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400/70" />
          <span className="text-xs font-mono text-zinc-600">/channels/adapters</span>
        </div>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
            <Globe size={16} className="text-zinc-400" strokeWidth={1.5} />
          </div>
          <div>
            <h2 className="text-[18px] font-medium tracking-tighter leading-none text-zinc-100">Platform Adapters</h2>
            <p className="text-sm text-zinc-600 mt-1">Connect messaging platforms for agent output delivery</p>
          </div>
        </div>
        <PlatformAdapterSettings />
      </div>
    </div>
  );
}
