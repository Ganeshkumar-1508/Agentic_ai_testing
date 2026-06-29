"use client";

import { usePipelineStore } from "@/stores/pipeline-store";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { api } from "@/lib/api/api-client";

export function ApprovalPanel() {
  const { approvals, mode } = usePipelineStore();
  const [shield, setShield] = useState(false);
  const [processing, setProcessing] = useState<Set<string>>(new Set());

  const handleApprove = async (id: string) => {
    setProcessing((prev) => new Set(prev).add(id));
    await api.post("/api/approve", { approval_id: id, approved: true });
    usePipelineStore.getState().approveRequest(id);
    setProcessing((prev) => { const next = new Set(prev); next.delete(id); return next; });
  };

  const handleDeny = async (id: string) => {
    setProcessing((prev) => new Set(prev).add(id));
    await api.post("/api/approve", { approval_id: id, approved: false });
    usePipelineStore.getState().denyRequest(id);
    setProcessing((prev) => { const next = new Set(prev); next.delete(id); return next; });
  };

  const handleShieldToggle = async () => {
    const next = !shield;
    setShield(next);
    await api.post("/api/shield", { active: next });
  };

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
          Approvals
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-2 py-0.5 rounded bg-white/[0.03] text-neutral-400 border border-white/[0.06]">
            {mode}
          </span>
          <button
            type="button"
            onClick={handleShieldToggle}
            className={cn(
              "text-[10px] px-2 py-0.5 rounded border transition-colors",
              shield
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-white/[0.03] border-white/[0.06] text-neutral-500 hover:text-neutral-300",
            )}
            title="Auto-approve all pending and future tool calls"
          >
            {shield ? "shield ON" : "shield OFF"}
          </button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {approvals.length === 0 ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center justify-center py-8 text-center"
          >
            <div className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-neutral-500">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <p className="text-xs text-neutral-500">No pending approvals</p>
          </motion.div>
        ) : (
          <motion.div key="list" className="space-y-2">
            {approvals.map((approval) => (
              <motion.div
                key={approval.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-3 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-neutral-100">{approval.tool}</span>
                  <span className="text-[10px] text-neutral-500 font-mono">{approval.id.slice(0, 8)}</span>
                </div>
                <div className="text-[10px] text-neutral-500 font-mono break-all">
                  {(JSON.stringify(approval.args) || "").slice(0, 200)}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleApprove(approval.id)}
                    disabled={processing.has(approval.id)}
                    className="flex-1 h-7 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-[11px] font-medium transition-colors active:scale-[0.98] disabled:opacity-50"
                  >
                    {processing.has(approval.id) ? "..." : "Approve"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeny(approval.id)}
                    disabled={processing.has(approval.id)}
                    className="flex-1 h-7 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] text-neutral-300 text-[11px] font-medium transition-colors active:scale-[0.98] disabled:opacity-50"
                  >
                    Deny
                  </button>
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
