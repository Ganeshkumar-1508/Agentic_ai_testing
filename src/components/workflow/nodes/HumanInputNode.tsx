"use client";

import { memo } from "react";
import { Handle, Position, NodeProps, Node } from "@xyflow/react";
import { UserRound } from "lucide-react";

type HumanInputData = Record<string, unknown> & {
  label: string;
  prompt?: string;
  config?: { options?: string[]; timeout_sec?: number };
};

export type HumanInputNodeType = Node<HumanInputData, "human_input">;

export const HumanInputNode = memo(function HumanInputNode({ data, selected }: NodeProps<HumanInputNodeType>) {
  return (
    <div className={`relative group ${selected ? "drop-shadow-[0_0_12px_rgba(139,92,246,0.25)]" : ""}`}>
      <Handle type="target" position={Position.Top}
        className="!w-2 !h-2 !bg-violet-400/60 !border-2 !border-zinc-900" />

      <div className={`
        min-w-[180px] rounded-xl border transition-all duration-200
        ${selected
          ? "border-violet-500/40 bg-gradient-to-b from-violet-500/8 to-violet-500/3 shadow-[inset_0_1px_0_rgba(139,92,246,0.08)]"
          : "border-zinc-800/50 bg-gradient-to-b from-zinc-900/80 to-zinc-950/80 hover:border-violet-700/50 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
        }
      `}>
        <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/30">
          <div className="w-5 h-5 rounded-md bg-violet-500/10 flex items-center justify-center">
            <UserRound size={10} className="text-violet-400" strokeWidth={1.5} />
          </div>
          <span className="text-[11px] font-medium text-zinc-200">{data.label || "Human Input"}</span>
          {data.config?.timeout_sec && (
            <code className="ml-auto text-[8px] px-1 py-0.5 rounded bg-zinc-800/60 text-zinc-500 font-mono">
              {(data.config.timeout_sec / 60).toFixed(0)}m
            </code>
          )}
        </div>
        <div className="px-3 py-2">
          {data.prompt ? (
            <p className="text-[10px] text-zinc-500 leading-relaxed line-clamp-2 font-mono">{data.prompt}</p>
          ) : (
            <p className="text-[10px] text-zinc-700 italic">No question defined</p>
          )}
          {data.config?.options && data.config.options.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {data.config.options.map((opt, i) => (
                <span key={i} className="text-[8px] px-1.5 py-0.5 rounded bg-zinc-800/60 text-zinc-500 font-mono">{opt}</span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 border-t border-zinc-800/20 bg-zinc-900/30">
          <span className="text-[8px] text-zinc-700 font-mono uppercase tracking-wider">human</span>
          <span className="text-[8px] text-zinc-700 font-mono ml-auto">HITL</span>
        </div>
      </div>

      <Handle type="source" position={Position.Bottom}
        className="!w-2 !h-2 !bg-violet-400/60 !border-2 !border-zinc-900" />
    </div>
  );
});
