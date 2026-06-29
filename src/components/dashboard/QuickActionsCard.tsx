"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { RefreshCw, Eye, ShieldAlert, AlertTriangle, Download } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface QuickActionsData {
  failed_rerun_count: number;
  pending_approvals: number;
  high_risk_flaky: number;
  watch_mode_default: boolean;
}

type Filter = "All" | "Passed" | "Failed" | "Flaky";

const FILTERS: Filter[] = ["All", "Passed", "Failed", "Flaky"];

export function QuickActionsCard() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("All");
  const [watchMode, setWatchMode] = useState(false);

  const { data, isLoading } = useQuery<QuickActionsData>({
    queryKey: ["dashboard-quick-actions"],
    queryFn: () => api.get<QuickActionsData>("/api/dashboard/widgets/quick-actions"),
    refetchInterval: 30_000,
  });

  const rerunMutation = useMutation({
    mutationFn: () => api.post<{ status: string; rerun: number }>("/api/dashboard/rerun-failed", { run_id: "" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
  });

  const counts = {
    rerun: data?.failed_rerun_count ?? 0,
    approvals: data?.pending_approvals ?? 0,
    flaky: data?.high_risk_flaky ?? 0,
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.95, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="card-label">Quick Actions</div>
        {data && (
          <div className="text-[10px] text-neutral-600">
            {counts.rerun + counts.approvals + counts.flaky} pending
          </div>
        )}
      </div>

      <div className="flex items-center gap-1 mb-3 shrink-0">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "px-2 py-0.5 text-[10px] rounded-md transition-colors",
              filter === f
                ? "bg-emerald-500/15 text-emerald-400"
                : "text-neutral-500 hover:text-neutral-300"
            )}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="space-y-1.5 flex-1 min-h-0">
        <ActionButton
          icon={<RefreshCw className="w-3.5 h-3.5" strokeWidth={1.5} />}
          label="Re-run failed tests"
          trailing={isLoading ? "…" : `${counts.rerun} failed`}
          trailingMono
          disabled={counts.rerun === 0}
          onClick={() => rerunMutation.mutate()}
          loading={rerunMutation.isPending}
        />
        <ActionButton
          icon={<Eye className="w-3.5 h-3.5" strokeWidth={1.5} />}
          label="Watch Mode"
          trailing={
            <span
              className={cn(
                "inline-block w-7 h-3.5 rounded-full relative transition-colors",
                watchMode ? "bg-emerald-500" : "bg-white/[0.08]"
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 w-2.5 h-2.5 rounded-full bg-white transition-transform",
                  watchMode ? "translate-x-3.5" : "translate-x-0.5"
                )}
              />
            </span>
          }
          onClick={() => setWatchMode(!watchMode)}
        />
        <ActionButton
          icon={<ShieldAlert className="w-3.5 h-3.5" strokeWidth={1.5} />}
          label="Approval Queue"
          trailing={
            counts.approvals > 0 ? (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">
                {counts.approvals} pending
              </span>
            ) : (
              <span className="text-[10px] text-neutral-600">0</span>
            )
          }
          disabled={counts.approvals === 0}
        />
        <ActionButton
          icon={<AlertTriangle className="w-3.5 h-3.5" strokeWidth={1.5} />}
          label="Flaky Prediction"
          trailing={
            counts.flaky > 0 ? (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">
                High Risk
              </span>
            ) : (
              <span className="text-[10px] text-neutral-600">Low</span>
            )
          }
          disabled={counts.flaky === 0}
        />
        <ActionButton
          icon={<Download className="w-3.5 h-3.5" strokeWidth={1.5} />}
          label="Export Report"
          trailing={<span className="text-[10px] text-neutral-600">CSV</span>}
          onClick={() => {
            if (typeof window !== "undefined") {
              window.open("/api/dashboard/overview", "_blank");
            }
          }}
        />
      </div>
    </motion.div>
  );
}

interface ActionButtonProps {
  icon: React.ReactNode;
  label: string;
  trailing?: React.ReactNode;
  trailingMono?: boolean;
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
}

function ActionButton({ icon, label, trailing, disabled, loading, onClick }: ActionButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[12px] transition-colors text-left",
        disabled
          ? "text-neutral-700 cursor-not-allowed"
          : "text-neutral-300 hover:bg-white/[0.04] hover:text-neutral-100"
      )}
    >
      <span className={cn(loading && "animate-spin", disabled ? "text-neutral-700" : "text-neutral-500")}>
        {icon}
      </span>
      <span className="flex-1">{label}</span>
      {trailing}
    </button>
  );
}
