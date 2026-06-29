"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { usePipelineStore } from "@/stores/pipeline-store";
import { Camera, RotateCcw, Tag, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  createSandboxSnapshot,
  restoreSandboxSnapshot,
  listSandboxSnapshots,
} from "@/lib/services/sandbox-client";

/** Parse a snapshot tag into a human-friendly label.
 *
 * Format: `testai-snapshot-<session12>-<label>-<hash>` or
 * `testai-snapshot-<session12>-<hash>` when no label was given.
 * We surface `<label>` (or `<hash>` as a fallback) and the timestamp
 * suffix for the user's mental model.
 */
function parseSnapshotTag(tag: string): { label: string; sessionSegment: string; hash: string } {
  const stripped = tag.replace(/^testai-snapshot-/, "");
  const parts = stripped.split("-");
  // Last 8 chars are the sha1[:8] hash; session is first 12 chars.
  const hash = parts.pop() || "";
  const sessionSegment = parts.shift() || "";
  const label = parts.length > 0 ? parts.join("-") : "(unlabeled)";
  return { label, sessionSegment, hash };
}

export function SandboxSnapshotPanel() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const status = usePipelineStore((s) => s.status);
  const [snapshots, setSnapshots] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [labelDraft, setLabelDraft] = useState("");
  const [showLabelInput, setShowLabelInput] = useState(false);

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const list = await listSandboxSnapshots(sessionId);
      setSnapshots(list);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    if ((status === "running" || status === "completed") && sessionId) {
      load();
    }
  }, [status, sessionId, load]);

  const handleSnapshot = async () => {
    if (!sessionId) return;
    setSnapshotting(true);
    try {
      const result = await createSandboxSnapshot(sessionId, labelDraft.trim());
      if (!result?.snapshot_id) {
        toast.error("Snapshot failed: no snapshot_id returned");
        return;
      }
      toast.success(
        labelDraft.trim()
          ? `Snapshot saved: ${result.snapshot_id.slice(0, 24)}…`
          : `Snapshot saved (unlabeled)`,
      );
      setLabelDraft("");
      setShowLabelInput(false);
      await load();
    } catch (e) {
      toast.error(`Snapshot failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSnapshotting(false);
    }
  };

  const handleRestore = async (snapshotId: string) => {
    setRestoring(snapshotId);
    try {
      const result = await restoreSandboxSnapshot(snapshotId);
      if (result?.session_id) {
        toast.success(
          `Restored as new session ${result.session_id.slice(0, 12)}…`,
        );
      }
    } catch (e) {
      toast.error(`Restore failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRestoring(null);
    }
  };

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
          Snapshots
        </div>
        <span className="text-[10px] font-mono text-neutral-700">
          {snapshots.length} saved
        </span>
      </div>

      {showLabelInput ? (
        <div className="flex items-center gap-1.5 mb-3">
          <input
            type="text"
            value={labelDraft}
            onChange={(e) => setLabelDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !snapshotting) handleSnapshot();
              if (e.key === "Escape") {
                setShowLabelInput(false);
                setLabelDraft("");
              }
            }}
            placeholder="Label (optional)"
            autoFocus
            disabled={snapshotting}
            className="flex-1 bg-white/[0.03] border border-white/[0.06] rounded-md px-2 py-1 text-[11px] text-neutral-200 placeholder-neutral-600 outline-none focus:border-emerald-500/40 transition-colors"
          />
          <button
            type="button"
            onClick={handleSnapshot}
            disabled={snapshotting}
            className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/6 border border-emerald-500/10 rounded-md px-2 py-1 hover:bg-emerald-500/10 transition-colors disabled:opacity-30"
          >
            {snapshotting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Camera className="w-3 h-3" />}
            Capture
          </button>
          <button
            type="button"
            onClick={() => {
              setShowLabelInput(false);
              setLabelDraft("");
            }}
            className="text-[10px] text-neutral-600 hover:text-neutral-400 px-1.5 py-1 transition-colors"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowLabelInput(true)}
          disabled={!sessionId || snapshotting}
          className="flex items-center gap-1.5 w-full text-[10px] text-emerald-400 bg-emerald-500/6 border border-emerald-500/10 rounded-md px-2.5 py-1.5 hover:bg-emerald-500/10 transition-colors disabled:opacity-30 mb-3"
        >
          <Plus className="w-3 h-3" strokeWidth={1.5} />
          Snapshot current state
        </button>
      )}

      {loading && snapshots.length === 0 ? (
        <div className="text-[11px] text-neutral-600 text-center py-3">Loading…</div>
      ) : snapshots.length === 0 ? (
        <div className="text-[11px] text-neutral-600 text-center py-3">
          No snapshots yet. Capture the current state to roll back to it later.
        </div>
      ) : (
        <div className="space-y-1">
          <AnimatePresence initial={false}>
            {snapshots.map((tag) => {
              const { label, hash } = parseSnapshotTag(tag);
              const isRestoring = restoring === tag;
              return (
                <motion.div
                  key={tag}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ type: "spring", stiffness: 200, damping: 25 }}
                  className="flex items-center gap-2 py-1.5 text-xs border-b border-white/[0.03] last:border-0"
                >
                  <Tag className="w-3 h-3 text-cyan-400 shrink-0" strokeWidth={1.5} />
                  <div className="flex-1 min-w-0">
                    <div className="text-neutral-300 truncate font-mono text-[11px]">{label}</div>
                    <div className="text-[9px] text-neutral-600 font-mono">…{hash}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRestore(tag)}
                    disabled={restoring !== null}
                    className="flex items-center gap-1 text-[10px] text-amber-400 bg-amber-500/6 border border-amber-500/10 rounded-md px-2 py-1 hover:bg-amber-500/10 transition-colors disabled:opacity-30"
                  >
                    {isRestoring ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <RotateCcw className="w-3 h-3" strokeWidth={1.5} />
                    )}
                    Restore
                  </button>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
