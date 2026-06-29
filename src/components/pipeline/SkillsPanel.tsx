"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Search } from "lucide-react";
import { api } from "@/lib/api/api-client";

export function SkillsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["skills"],
    queryFn: async () => {
      const j = await api.get<{ skills?: { name: string; description?: string; version?: string }[] }>(`/api/admin/skills`);
      return (j?.skills || []) as { name: string; description?: string; version?: string }[];
    },
  });

  const skills = (data || []).slice(0, 15);

  return (
    <div className="bg-card border border-white/[0.06] rounded-xl p-4">
      <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Skills</div>
      <div className="relative mb-3">
        <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-zinc-600" strokeWidth={1.5} />
        <input placeholder="Search skills..."         className="w-full pl-8 pr-3 py-2 text-[13px] bg-card border border-white/[0.06] rounded-lg text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/30" />
      </div>
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-16 rounded-lg shimmer-bg" />)}
        </div>
      ) : skills.length === 0 ? (
        <div className="text-center py-6 text-[12px] text-zinc-600">
          <BookOpen className="w-6 h-6 mx-auto mb-2 text-zinc-700" strokeWidth={1} />
          <p>No skills loaded</p>
          <p className="text-[11px] text-zinc-700 mt-1">Skills are loaded at runtime by agents via the skill tool</p>
        </div>
      ) : (
        <div className="space-y-1 max-h-[400px] overflow-y-auto">
          {skills.map((sk, i) => (
            <div key={sk.name || i} className="flex items-start gap-3 p-3 rounded-lg hover:bg-white/[0.03] cursor-pointer transition-colors border border-transparent hover:border-white/[0.06]">
              <div className="w-8 h-8 rounded-lg bg-surface-elevated border border-white/[0.06] flex items-center justify-center shrink-0">
                <BookOpen className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold text-zinc-200 flex items-center gap-1.5">
                  {sk.name}
                  {sk.version && <span className="text-[10px] font-mono text-zinc-600 px-1.5 py-0.5 rounded-full bg-white/[0.05]">{sk.version}</span>}
                </div>
                <div className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{sk.description || ""}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
