"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import Link from "next/link";
import { Bot, Plus, Settings, ChevronRight } from "lucide-react";
import { listAgents, type Agent } from "@/lib/api/agents";

export default function AgentsPage() {
  const { data: agents, isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents,
  });

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
            <span className="text-xs font-mono text-zinc-600">/agents</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><Bot size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
            <div>
              <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Agents</h1>
              <p className="text-sm text-zinc-600 mt-1">Manage your custom agent configurations</p>
            </div>
          </div>
        </div>
        <Link href="/agents/new" className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-all active:scale-[0.97]">
          <Plus size={14} strokeWidth={1.5} /> New Agent
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 rounded-2xl shimmer-bg" />)}</div>
      ) : !agents?.length ? (
        <div className="text-center py-16 text-zinc-600 space-y-3">
          <Bot size={32} className="mx-auto text-zinc-700" strokeWidth={1} />
          <p className="text-sm">No custom agents yet</p>
          <Link href="/agents/new" className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300">Create your first agent</Link>
        </div>
      ) : (
        <div className="grid gap-3">
          {(agents as Agent[]).map((agent, i) => (
            <Link key={agent.name} href={`/agents/${encodeURIComponent(agent.name)}`}>
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-5 hover:bg-zinc-900/60 hover:border-zinc-700/50 transition-all group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-zinc-800/50 flex items-center justify-center"><Bot size={18} className="text-zinc-400" strokeWidth={1.5} /></div>
                    <div>
                      <h3 className="text-sm font-medium text-zinc-200">{agent.name}</h3>
                      <p className="text-xs text-zinc-500 mt-0.5">{agent.description || `Custom agent`}</p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="text-[10px] font-mono text-zinc-600">{agent.tools?.length || 0} tools</span>
                        {agent.model && <span className="text-[10px] font-mono text-zinc-600">· {agent.model}</span>}
                        {agent.skills?.length ? <span className="text-[10px] font-mono text-zinc-600">· {agent.skills.length} skills</span> : null}
                      </div>
                    </div>
                  </div>
                  <ChevronRight size={16} className="text-zinc-700 group-hover:text-zinc-500 transition-colors" strokeWidth={1.5} />
                </div>
              </motion.div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
