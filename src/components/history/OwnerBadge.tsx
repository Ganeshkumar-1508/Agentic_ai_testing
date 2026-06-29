"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";

interface OwnerPattern {
  teamName: string;
  pattern: string;
}

function matchOwner(testName: string, patterns: OwnerPattern[]): string | null {
  for (let i = patterns.length - 1; i >= 0; i--) {
    const { pattern, teamName } = patterns[i];
    const pat = pattern.endsWith("/") ? `${pattern}**` : pattern;
    let regexStr = pat
      .replace(/\./g, "\\.")
      .replace(/\*\*/g, ".*")
      .replace(/\*/g, "[^/]*")
      .replace(/\?/g, ".");
    try {
      if (new RegExp(regexStr).test(testName)) return teamName;
    } catch { /* ignore */ }
  }
  return null;
}

const TEAM_COLORS: Record<string, string> = {
  frontend: "bg-blue-500/10 text-blue-400",
  backend: "bg-emerald-500/10 text-emerald-400",
  infra: "bg-zinc-500/10 text-zinc-400",
  data: "bg-amber-500/10 text-amber-400",
  mobile: "bg-zinc-500/10 text-zinc-400",
  security: "bg-red-500/10 text-red-400",
  qa: "bg-zinc-500/10 text-zinc-400",
  docs: "bg-zinc-500/10 text-zinc-400",
  core: "bg-zinc-500/10 text-zinc-500",
};

export function OwnerBadge({ testName, repoUrl }: { testName: string; repoUrl?: string }) {
  const { data } = useQuery({
    queryKey: ["test-owners", repoUrl],
    queryFn: async () => {
      if (!repoUrl) return [];
      const json = await api.get<{ patterns: OwnerPattern[] }>(`/api/tests/owners/batch?repo_url=${encodeURIComponent(repoUrl)}`);
      return json?.patterns ?? [];
    },
    enabled: !!repoUrl,
    staleTime: 300_000,
  });

  const owner = useMemo(() => {
    if (!data || data.length === 0) return null;
    return matchOwner(testName, data);
  }, [testName, data]);

  if (!owner || owner === "core") return null;

  const colorClass = TEAM_COLORS[owner.toLowerCase()] ?? "bg-zinc-500/10 text-zinc-400";

  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium font-mono ${colorClass}`}>
      @{owner}
    </span>
  );
}
