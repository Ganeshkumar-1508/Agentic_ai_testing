"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Shield, ShieldCheck, ShieldOff, Search } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api/api-client";

interface ToolPerm {
  name: string;
  level: "allow" | "ask" | "deny";
  default: "allow" | "ask" | "deny";
  description: string;
}

const LEVEL_ICONS = { allow: ShieldCheck, ask: Shield, deny: ShieldOff };
const LEVEL_COLORS = { allow: "text-emerald-400", ask: "text-amber-400", deny: "text-red-400" };
const LEVEL_BG = { allow: "bg-emerald-500/10", ask: "bg-amber-500/10", deny: "bg-red-500/10" };

function LevelBadge({ level }: { level: string }) {
  const Icon = LEVEL_ICONS[level as keyof typeof LEVEL_ICONS] ?? Shield;
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider",
      LEVEL_BG[level as keyof typeof LEVEL_BG] ?? "bg-zinc-800", LEVEL_COLORS[level as keyof typeof LEVEL_COLORS] ?? "text-zinc-500")}>
      <Icon className="w-3 h-3" strokeWidth={1.5} />
      {level}
    </span>
  );
}

export function ToolPermissionsManager() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["tool-permissions"],
    queryFn: async () => {
      const json = await api.get<{ tools: ToolPerm[] }>(`/api/permissions/tools`);
      return json?.tools ?? [];
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ tool_name, level }: { tool_name: string; level: string }) =>
      api.post(`/api/permissions/tools`, { tool_name, level }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["tool-permissions"] }); toast.success("Permission updated"); },
    onError: () => toast.error("Failed to update"),
  });

  const tools = (data ?? []).filter((t) =>
    !search || t.name.toLowerCase().includes(search.toLowerCase()) || (t.description || "").toLowerCase().includes(search.toLowerCase())
  );

  const nextLevel = (current: string) => current === "allow" ? "ask" : current === "ask" ? "deny" : "allow";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-zinc-800/40 border border-white/[0.05]">
        <Search className="w-3.5 h-3.5 text-zinc-600 shrink-0" strokeWidth={1.5} />
        <input value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search tools..."
          className="flex-1 bg-transparent text-xs text-zinc-300 placeholder:text-zinc-700 outline-none font-mono" />
        <span className="text-[10px] text-zinc-600 font-mono">{tools.length} tools</span>
      </div>
      <div className="space-y-1">
        {isLoading ? (
          [1, 2, 3, 4, 5].map((i) => <div key={i} className="h-12 rounded-xl shimmer-bg" />)
        ) : tools.length === 0 ? (
          <div className="py-10 text-center text-xs text-zinc-600">No tools found</div>
        ) : (
          tools.map((tool, i) => {
            const Icon = LEVEL_ICONS[tool.level];
            return (
              <motion.div key={tool.name} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.008, duration: 0.2 }}
                className="flex items-center gap-3 px-4 py-2.5 rounded-xl bg-white/[0.01] border border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
                <Icon className={cn("w-4 h-4 shrink-0", LEVEL_COLORS[tool.level])} strokeWidth={1.5} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-semibold text-zinc-200">{tool.name}</span>
                    <LevelBadge level={tool.level} />
                    {tool.level !== tool.default && (
                      <span className="text-[8px] text-zinc-700 font-mono">default: {tool.default}</span>
                    )}
                  </div>
                  <div className="text-[10px] text-zinc-600 truncate">{tool.description}</div>
                </div>
                <button onClick={() => updateMut.mutate({ tool_name: tool.name, level: nextLevel(tool.level) })}
                  className="px-2 py-1 rounded-lg text-[9px] text-zinc-600 hover:text-zinc-300 hover:bg-white/[0.04] transition-colors font-mono">
                  {nextLevel(tool.level)}
                </button>
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
}
