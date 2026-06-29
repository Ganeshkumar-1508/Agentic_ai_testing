"use client";

import { memo } from "react";
import { Handle, Position, NodeProps, Node } from "@xyflow/react";
import { GitFork } from "lucide-react";

interface BranchRule {
  label: string;
  condition: string;
  target_step: string;
}

type RouterData = Record<string, unknown> & {
  label: string;
  prompt?: string;
  branch_rules?: BranchRule[];
};

export type RouterNodeType = Node<RouterData, "router">;

export const RouterNode = memo(function RouterNode({ data, selected }: NodeProps<RouterNodeType>) {
  const rules = data.branch_rules || [];
  return (
    <div className={`relative group ${selected ? "drop-shadow-[0_0_12px_rgba(217,119,6,0.25)]" : ""}`}>
      <Handle type="target" position={Position.Top}
        className="!w-2 !h-2 !bg-amber-400/60 !border-2 !border-zinc-900" />

      <div className={`
        min-w-[180px] rounded-xl border transition-all duration-200
        ${selected
          ? "border-amber-500/40 bg-gradient-to-b from-amber-500/8 to-amber-500/3 shadow-[inset_0_1px_0_rgba(217,119,6,0.08)]"
          : "border-zinc-800/50 bg-gradient-to-b from-zinc-900/80 to-zinc-950/80 hover:border-amber-700/50 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
        }
      `}>
        <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/30">
          <div className="w-5 h-5 rounded-md bg-amber-500/10 flex items-center justify-center">
            <GitFork size={10} className="text-amber-400" strokeWidth={1.5} />
          </div>
          <span className="text-[11px] font-medium text-zinc-200">{data.label || "Router"}</span>
        </div>
        <div className="px-3 py-2 space-y-1">
          {rules.length > 0 ? (
            rules.map((rule, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[9px]">
                <span className="w-1 h-1 rounded-full bg-amber-400/60 shrink-0" />
                <span className="text-zinc-500 font-mono">{rule.label}</span>
                <span className="text-zinc-700 font-mono">→ {rule.target_step}</span>
              </div>
            ))
          ) : (
            <p className="text-[10px] text-zinc-700 italic">No branch rules defined</p>
          )}
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 border-t border-zinc-800/20 bg-zinc-900/30">
          <span className="text-[8px] text-zinc-700 font-mono uppercase tracking-wider">router</span>
          <span className="text-[8px] text-zinc-700 font-mono ml-auto">{rules.length} rules</span>
        </div>
      </div>

      <Handle type="source" position={Position.Bottom}
        className="!w-2 !h-2 !bg-amber-400/60 !border-2 !border-zinc-900" />
      <Handle type="source" position={Position.Right} id="true"
        className="!w-2 !h-2 !bg-emerald-400/60 !border-2 !border-zinc-900" />
      <Handle type="source" position={Position.Left} id="false"
        className="!w-2 !h-2 !bg-red-400/60 !border-2 !border-zinc-900" />
    </div>
  );
});
