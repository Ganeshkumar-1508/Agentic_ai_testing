"use client";

import { memo, useCallback } from "react";
import { Handle, Position, NodeProps, Node } from "@xyflow/react";
import { Cpu, GripVertical } from "lucide-react";

type AgentTaskData = Record<string, unknown> & {
  label: string;
  prompt?: string;
  config?: { model?: string; toolsets?: string[] };
};

export type AgentTaskNodeType = Node<AgentTaskData, "agent">;

export const AgentTaskNode = memo(function AgentTaskNode({ data, selected }: NodeProps<AgentTaskNodeType>) {
  return (
    <div className={`relative group ${selected ? "drop-shadow-[0_0_12px_rgba(52,211,153,0.25)]" : ""}`}>
      <Handle type="target" position={Position.Top}
        className="!w-2 !h-2 !bg-emerald-400/60 !border-2 !border-zinc-900" />

      <div className={`
        min-w-[180px] rounded-xl border transition-all duration-200
        ${selected
          ? "border-emerald-500/40 bg-gradient-to-b from-emerald-500/8 to-emerald-500/3 shadow-[inset_0_1px_0_rgba(52,211,153,0.08)]"
          : "border-zinc-800/50 bg-gradient-to-b from-zinc-900/80 to-zinc-950/80 hover:border-zinc-700/50 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
        }
      `}>
        <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/30">
          <div className="w-5 h-5 rounded-md bg-emerald-500/10 flex items-center justify-center">
            <Cpu size={10} className="text-emerald-400" strokeWidth={1.5} />
          </div>
          <span className="text-[11px] font-medium text-zinc-200">{data.label || "Agent Task"}</span>
          {data.config?.model && (
            <code className="ml-auto text-[8px] px-1 py-0.5 rounded bg-zinc-800/60 text-zinc-500 font-mono">{data.config.model}</code>
          )}
        </div>
        <div className="px-3 py-2">
          {data.prompt ? (
            <p className="text-[10px] text-zinc-500 leading-relaxed line-clamp-2 font-mono">{data.prompt}</p>
          ) : (
            <p className="text-[10px] text-zinc-700 italic">No prompt defined</p>
          )}
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 border-t border-zinc-800/20 bg-zinc-900/30">
          <span className="text-[8px] text-zinc-700 font-mono uppercase tracking-wider">agent</span>
          {data.config?.toolsets && data.config.toolsets.length > 0 && (
            <span className="text-[8px] text-zinc-700 font-mono ml-auto">
              {data.config.toolsets.join(", ")}
            </span>
          )}
        </div>
      </div>

      <Handle type="source" position={Position.Bottom}
        className="!w-2 !h-2 !bg-emerald-400/60 !border-2 !border-zinc-900" />
    </div>
  );
});
