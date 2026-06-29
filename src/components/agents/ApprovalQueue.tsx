"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Check,
  X,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api/api-client";

interface ApprovalItem {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  status: string;
}

interface ApprovalQueueProps {
  sessionId: string;
  onApprove?: (id: string, scope: "once" | "session" | "always") => void;
  onDeny?: (id: string) => void;
}

export function ApprovalQueue({ sessionId, onApprove, onDeny }: ApprovalQueueProps) {
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [resolving, setResolving] = useState<Record<string, boolean>>({});

  const fetchApprovals = useCallback(async () => {
    try {
      const data = await api.get<{ approvals?: ApprovalItem[] }>("/api/delegate/approvals/pending");
      setApprovals(data?.approvals || []);
    } catch {
      // Silently retry
    }
  }, []);

  useEffect(() => {
    fetchApprovals();
    const interval = setInterval(fetchApprovals, 2000);
    return () => clearInterval(interval);
  }, [fetchApprovals]);

  const handleAction = async (
    approvalId: string,
    approved: boolean,
    scope: "once" | "session" | "always"
  ) => {
    setResolving((prev) => ({ ...prev, [approvalId]: true }));
    try {
      await api.post("/api/delegate/approve", { approval_id: approvalId, approved, scope });
      if (approved) onApprove?.(approvalId, scope);
      else onDeny?.(approvalId);
    } catch {
      // Handle error
    } finally {
      setResolving((prev) => ({ ...prev, [approvalId]: false }));
      fetchApprovals();
    }
  };

  if (approvals.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-amber-600">
        <AlertTriangle className="h-4 w-4" />
        <span>Pending Approvals ({approvals.length})</span>
      </div>
      {approvals.map((item) => (
        <div
          key={item.id}
          className="rounded-lg border border-amber-200/50 bg-amber-50/30 p-4 text-sm"
        >
          <div className="mb-3 flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="font-medium text-zinc-800">
                {item.tool}
              </div>
              <pre className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap break-all rounded bg-white/50 p-2 text-xs text-zinc-600">
                {JSON.stringify(item.args, null, 2)}
              </pre>
            </div>
            <span className="flex items-center gap-1 whitespace-nowrap text-xs text-zinc-400">
              <Clock className="h-3 w-3" />
              pending
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleAction(item.id, true, "once")}
              disabled={resolving[item.id]}
              className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-all hover:bg-emerald-700 active:scale-[0.98] disabled:opacity-50"
            >
            <Check className="h-3.5 w-3.5" />
            Approve Once
            </button>
            <button
              onClick={() => handleAction(item.id, true, "session")}
              disabled={resolving[item.id]}
              className="inline-flex items-center gap-1.5 rounded-md border border-emerald-300 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 transition-all hover:bg-emerald-50 active:scale-[0.98] disabled:opacity-50"
            >
            <Check className="h-3.5 w-3.5" />
            Session
            </button>
            <button
              onClick={() => handleAction(item.id, true, "always")}
              disabled={resolving[item.id]}
              className="inline-flex items-center gap-1.5 rounded-md border border-emerald-300 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 transition-all hover:bg-emerald-50 active:scale-[0.98] disabled:opacity-50"
            >
            <Check className="h-3.5 w-3.5" />
            Always
            </button>
            <button
              onClick={() => handleAction(item.id, false, "once")}
              disabled={resolving[item.id]}
              className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 transition-all hover:bg-red-50 active:scale-[0.98] disabled:opacity-50"
            >
              <X className="h-3.5 w-3.5" />
              Deny
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
