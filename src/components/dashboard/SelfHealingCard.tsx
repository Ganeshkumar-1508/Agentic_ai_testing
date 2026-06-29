"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface HealingEvent {
  id: string;
  test_name: string;
  old_locator: string;
  new_locator: string;
  strategy: string;
  confidence: number;
  passed: boolean;
  created_at: string;
}

interface SelfHealingData {
  active: boolean;
  success_rate: number;
  total_attempts: number;
  succeeded: number;
  events: HealingEvent[];
  count: number;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  return `${Math.floor(hr / 24)}d`;
}

function fileFromTestName(name: string): string {
  if (!name) return "";
  const slash = name.lastIndexOf("/");
  const base = slash >= 0 ? name.slice(slash + 1) : name;
  return base.replace(/\s+/g, "-");
}

export function SelfHealingCard() {
  const { data, isLoading } = useQuery<SelfHealingData>({
    queryKey: ["dashboard-self-healing"],
    queryFn: () => api.get<SelfHealingData>("/api/dashboard/widgets/self-healing"),
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="flex items-center justify-between">
          <div className="w-24 h-4 rounded shimmer-bg" />
          <div className="w-16 h-4 rounded-full shimmer-bg" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-5 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  const successRate = data?.success_rate ?? 0;
  const isActive = data?.active ?? false;
  const events = data?.events ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.45, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Self-Healing</div>
        <div className="text-[11px] font-mono text-neutral-400">
          {data?.total_attempts ? `${successRate}% success` : "—"}
        </div>
      </div>

      <div className="flex items-center gap-2 mb-4 shrink-0">
        <span className={cn("w-2 h-2 rounded-full", isActive ? "bg-emerald-400 animate-pulse" : "bg-neutral-700")} />
        <span className="text-xs text-neutral-300">{isActive ? "Active" : "Idle"}</span>
        {data && data.total_attempts > 0 && (
          <span className="ml-auto text-[10px] font-mono text-neutral-600">
            {data.succeeded}/{data.total_attempts} healed
          </span>
        )}
      </div>

      {events.length === 0 ? (
        <div className="text-xs text-neutral-600 text-center py-6 flex-1 flex items-center justify-center">No healing events yet.</div>
      ) : (
        <div className="space-y-2.5 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
          {events.slice(0, 4).map((e, i) => {
            const file = fileFromTestName(e.test_name);
            return (
              <motion.div
                key={e.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5 + i * 0.04 }}
                className="flex items-center gap-2 text-[11px]"
              >
                <span
                  className={cn(
                    "w-1.5 h-1.5 rounded-full shrink-0",
                    e.passed ? "bg-emerald-400" : "bg-red-400"
                  )}
                />
                <span className="flex-1 text-neutral-400 truncate">
                  {e.passed ? "Healed" : "Failed to heal"}{" "}
                  <code className="font-mono text-[10.5px] px-1 py-0.5 rounded bg-emerald-500/10 text-emerald-400 ml-0.5">
                    {file}
                  </code>
                </span>
                <span className="text-neutral-600 font-mono shrink-0">{timeAgo(e.created_at)}</span>
              </motion.div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
