"use client";

import { Coins } from "lucide-react";

interface TokenUsage {
  input: number;
  output: number;
  total: number;
}

function format(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return `${n}`;
}

interface TokenUsageBadgeProps {
  usage: TokenUsage | null;
  enabled?: boolean;
}

export function TokenUsageBadge({ usage, enabled = false }: TokenUsageBadgeProps) {
  if (!enabled || !usage || usage.total === 0) return null;

  return (
    <div className="flex items-center gap-1.5 rounded-full border border-zinc-800/30 bg-zinc-900/50 px-2.5 py-1 text-[10px] font-mono text-zinc-500">
      <Coins size={11} strokeWidth={1.5} className="text-zinc-600" />
      <span>{format(usage.total)} total</span>
      <span className="text-zinc-700">·</span>
      <span className="text-zinc-600">+{format(usage.output)} out</span>
    </div>
  );
}
