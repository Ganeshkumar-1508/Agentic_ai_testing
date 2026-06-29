"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { DollarSign, Cpu, Brain, Wrench, ShieldCheck, Globe, Terminal, Activity } from "lucide-react";
import { api } from "@/lib/api/api-client";

const ROLE_CONFIG: Record<string, { icon: typeof Brain; color: string }> = {
  explorer: { icon: Globe, color: "text-blue-400" },
  "fix-engineer": { icon: Wrench, color: "text-emerald-400" },
  reviewer: { icon: ShieldCheck, color: "text-zinc-400" },
  "setup-engineer": { icon: Terminal, color: "text-amber-400" },
  "test-runner": { icon: Activity, color: "text-zinc-400" },
};

const ROLE_LABELS: Record<string, string> = {
  explorer: "Explore",
  "fix-engineer": "Fix",
  reviewer: "Review",
  "setup-engineer": "Setup",
  "test-runner": "Test",
};

export function CostBreakdownCard() {
  const { data } = useQuery({
    queryKey: ["cost-per-role"],
    queryFn: () => api.get<any>("/api/cost/per-role?days=7"),
    refetchInterval: 120_000,
  });

  const roles = (data?.roles ?? []) as Array<{
    agent_role: string; total_cost: number; total_input: number; total_output: number; total_calls: number;
  }>;
  const totalCost = data?.total_cost ?? 0;

  return (
    <div className="bg-card border border-white/[0.06] rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Cost by Agent Role</span>
        </div>
        <span className="text-[11px] font-mono text-zinc-500">
          ${totalCost.toFixed(4)} total
        </span>
      </div>

      {roles.length === 0 ? (
        <div className="py-6 text-center">
          <DollarSign className="w-5 h-5 mx-auto mb-2 text-zinc-700" strokeWidth={1.5} />
          <p className="text-[12px] text-zinc-600">No cost data yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {roles.map((role, i) => {
            const cfg = ROLE_CONFIG[role.agent_role] || { icon: Brain, color: "text-zinc-400" };
            const Icon = cfg.icon;
            const pct = totalCost > 0 ? (role.total_cost / totalCost) * 100 : 0;
            const label = ROLE_LABELS[role.agent_role] || role.agent_role;

            return (
              <motion.div
                key={role.agent_role}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05, type: "spring", stiffness: 100, damping: 20 }}
              >
                <div className="flex items-center gap-3 mb-1">
                  <div className={`w-7 h-7 rounded-lg bg-white/[0.03] flex items-center justify-center ${cfg.color}`}>
                    <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] font-medium text-zinc-200">{label}</span>
                      <span className="text-[12px] font-mono text-zinc-300">${role.total_cost.toFixed(4)}</span>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-zinc-600 font-mono mt-0.5">
                      <span>{role.total_calls} calls</span>
                      <span>{(role.total_input + role.total_output).toLocaleString()}t</span>
                    </div>
                  </div>
                </div>
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500 rounded-full transition-all duration-700" style={{ width: `${pct}%` }} />
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
