"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import { Puzzle } from "lucide-react";

export function MCPStatus() {
  const { data: connections } = useQuery({
    queryKey: ["mcp-status"],
    queryFn: async () => {
      const json = await api.get<{ connections: Array<{ id: string; name: string; connected: boolean; tools: Array<{ name: string }>; error?: string }> }>(`/api/settings/mcp/connections`);
      return json?.connections ?? [];
    },
    staleTime: 15_000,
  });

  const connected = connections?.filter((c) => c.connected).length ?? 0;
  const total = connections?.length ?? 0;

  return (
    <div className="px-4 py-3 border-t border-border">
      <div className="flex items-center gap-2 text-xs">
        <Puzzle className="w-3 h-3 text-neutral-500 shrink-0" strokeWidth={1.5} />
        <span className="text-muted-foreground">
          {total > 0 ? `${connected}/${total} MCP` : "No MCP servers"}
        </span>
        {total > 0 && (
          <span className={cn("w-1.5 h-1.5 rounded-full", connected === total ? "bg-emerald-400" : connected > 0 ? "bg-amber-400" : "bg-red-400")} />
        )}
      </div>
      {connections && connections.length > 0 && (
        <div className="mt-1.5 space-y-1">
          {connections.slice(0, 3).map((conn) => (
            <div key={conn.id} className="flex items-center gap-2 text-[10px] text-muted-foreground">
              <span className={cn("w-1 h-1 rounded-full", conn.connected ? "bg-emerald-400" : "bg-red-400")} />
              <span className="truncate">{conn.name}</span>
              <span className="text-neutral-600">({conn.tools?.length ?? 0} tools)</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
