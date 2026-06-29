"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";
import { Shield } from "lucide-react";

export function ApprovalBadge() {
  const { data } = useQuery({
    queryKey: ["approval-count"],
    queryFn: async () => {
      try {
        const json = await api.get<{ pending: any[] }>(`/api/permissions/pending`);
        return json?.pending ?? [];
      } catch {
        return [];
      }
    },
    refetchInterval: 10_000,
  });

  const count = data?.length ?? 0;

  if (count === 0) return null;

  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-500/10 border border-amber-500/20">
      <Shield className="w-3 h-3 text-amber-400 shrink-0" strokeWidth={1.5} />
      <span className="text-[10px] text-amber-400 font-medium tabular-nums">{count} pending</span>
    </div>
  );
}
