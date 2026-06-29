"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, Trash2, Sparkles, ExternalLink, AlertCircle, Beaker, GitBranch, Bug } from "lucide-react";
import { useEffect } from "react";
import { cn } from "@/lib/utils";
import type { Requirement, TestCase, Defect, Priority, ReqStatus } from "./types";
import { REQ_STATUS_TONE, PRIORITY_TONE, TEST_STATUS_TONE, TEST_TYPE_LABEL, NODE_KIND_TONE } from "./constants";
import { useRequirementDetail, useUnlinkTest, useDeleteRequirement, useUpdateRequirement, useGenerateTests } from "./use-traceability";

export type InspectorSelection =
  | { kind: "requirement"; id: string }
  | { kind: "test"; id: string; reqId: string; testStatus: import("./types").TestStatus }
  | { kind: "defect"; id: string; testName: string | null; status: string | null; reqId: string | null }
  | { kind: "gap"; id: string; reqId: string }
  | null;

export function InspectorDrawer({
  selection,
  onClose,
  onEdit,
  onSelectTest,
  onSelectRequirement,
}: {
  selection: InspectorSelection;
  onClose: () => void;
  onEdit: (req: Requirement) => void;
  onSelectTest: (testId: string, reqId: string) => void;
  onSelectRequirement: (reqId: string) => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <AnimatePresence>
      {selection && (
        <>
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px]"
          />
          <motion.aside
            key="drawer"
            initial={{ x: 420, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 420, opacity: 0 }}
            transition={{ type: "spring", stiffness: 120, damping: 22 }}
            className="fixed top-0 right-0 bottom-0 w-full sm:w-[420px] z-50 bg-surface border-l border-white/[0.08] flex flex-col"
            style={{
              boxShadow: "inset 1px 0 0 rgba(255,255,255,0.04), -16px 0 40px rgba(0,0,0,0.4)",
            }}
          >
            <DrawerHeader selection={selection} onClose={onClose} onEdit={onEdit} />
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {selection.kind === "requirement" && (
                <RequirementInspector id={selection.id} onEdit={onEdit} onSelectTest={onSelectTest} />
              )}
              {selection.kind === "test" && (
                <TestInspector
                  testId={selection.id}
                  reqId={selection.reqId}
                  testStatus={selection.testStatus}
                  onSelectRequirement={onSelectRequirement}
                />
              )}
              {selection.kind === "defect" && (
                <DefectInspector
                  defectId={selection.id}
                  testName={selection.testName}
                  reqId={selection.reqId}
                  onSelectRequirement={onSelectRequirement}
                />
              )}
              {selection.kind === "gap" && <GapInspector reqId={selection.reqId} />}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function DrawerHeader({
  selection,
  onClose,
  onEdit,
}: {
  selection: InspectorSelection;
  onClose: () => void;
  onEdit: (req: Requirement) => void;
}) {
  const tone = selection ? NODE_KIND_TONE[selectionKindToNodeKind(selection)] : NODE_KIND_TONE.requirement;
  const detailQ = useRequirementDetail(selection?.kind === "requirement" ? selection.id : null);
  const deleteMut = useDeleteRequirement();
  const updateMut = useUpdateRequirement();

  return (
    <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between gap-3">
      <div className="flex items-center gap-2.5 min-w-0">
        <span
          className={cn(
            "w-2 h-2 rounded-full shrink-0",
            selection?.kind === "requirement" && "bg-zinc-400",
            selection?.kind === "test" && "bg-emerald-400",
            selection?.kind === "defect" && "bg-rose-400",
            selection?.kind === "gap" && "bg-rose-400/40"
          )}
        />
        <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider truncate">
          {selection?.kind === "requirement" && "Requirement"}
          {selection?.kind === "test" && "Test case"}
          {selection?.kind === "defect" && "Defect"}
          {selection?.kind === "gap" && "Coverage gap"}
        </span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {selection?.kind === "requirement" && detailQ.data?.requirement && (
          <>
            <button
              onClick={() => onEdit(detailQ.data.requirement)}
              className="text-[11px] font-mono text-neutral-500 hover:text-emerald-300 transition-colors px-2 py-1"
            >
              Edit
            </button>
            <button
              onClick={() => {
                if (confirm("Delete this requirement? This will unlink all tests.")) {
                  deleteMut.mutate({ id: detailQ.data.requirement.id });
                }
              }}
              className="text-[11px] font-mono text-neutral-500 hover:text-rose-300 transition-colors px-2 py-1 flex items-center gap-1"
            >
              <Trash2 className="w-3 h-3" strokeWidth={1.5} />
            </button>
            {detailQ.data.requirement.status === "active" && (
              <button
                onClick={() =>
                  updateMut.mutate({ id: detailQ.data.requirement.id, status: "archived" })
                }
                className="text-[11px] font-mono text-neutral-500 hover:text-amber-300 transition-colors px-2 py-1"
              >
                Archive
              </button>
            )}
          </>
        )}
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded-md text-neutral-500 hover:text-neutral-200 hover:bg-white/[0.04] transition-colors"
          aria-label="Close inspector"
        >
          <X className="w-3.5 h-3.5" strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}

function selectionKindToNodeKind(s: InspectorSelection): import("./types").GraphNodeKind {
  if (s?.kind === "requirement") return "requirement";
  if (s?.kind === "test") return "test";
  if (s?.kind === "defect") return "defect";
  if (s?.kind === "gap") return "gap";
  return "requirement";
}

function RequirementInspector({
  id,
  onEdit,
  onSelectTest,
}: {
  id: string;
  onEdit: (req: Requirement) => void;
  onSelectTest: (testId: string, reqId: string) => void;
}) {
  const q = useRequirementDetail(id);
  const unlink = useUnlinkTest();
  const generate = useGenerateTests();

  if (q.isLoading) return <SkeletonRows />;
  if (q.error || !q.data) {
    return (
      <div className="text-[12px] text-neutral-500 flex items-center gap-2">
        <AlertCircle className="w-3.5 h-3.5 text-rose-400" strokeWidth={1.5} />
        Failed to load requirement.
      </div>
    );
  }

  const req = q.data.requirement;
  const tests = q.data.tests;
  const priority = PRIORITY_TONE[req.priority as Priority];
  const status = REQ_STATUS_TONE[req.status as ReqStatus];

  return (
    <>
      <div>
        <div className="flex items-center gap-2 mb-2">
          <GitBranch className="w-3.5 h-3.5 text-zinc-300" strokeWidth={1.5} />
          <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">Title</span>
        </div>
        <h2 className="text-[18px] font-semibold text-neutral-100 leading-snug">{req.title}</h2>
        {req.description && (
          <p className="text-[13px] text-neutral-400 leading-relaxed mt-2">{req.description}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat label="Priority" tone={priority.text}>
          <span className="flex items-center gap-1.5">
            <span className={cn("w-1.5 h-1.5 rounded-full", priority.dot)} />
            {priority.label}
          </span>
        </Stat>
        <Stat label="Status" tone={status.text}>
          <span className="flex items-center gap-1.5">
            <span className={cn("w-1.5 h-1.5 rounded-full", status.dot)} />
            {status.label}
          </span>
        </Stat>
        <Stat label="Tests linked" tone="text-neutral-200">{tests.length}</Stat>
        <Stat label="Source" tone="text-neutral-300">{req.source ?? "manual"}</Stat>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Beaker className="w-3.5 h-3.5 text-emerald-300" strokeWidth={1.5} />
            <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">
              Linked Tests ({tests.length})
            </span>
          </div>
          <button
            onClick={() => generate.mutate({ requirement_ids: [req.id] })}
            disabled={generate.isPending}
            className="text-[10.5px] font-mono text-emerald-400 hover:text-emerald-300 transition-colors flex items-center gap-1 disabled:opacity-50"
          >
            <Sparkles className="w-3 h-3" strokeWidth={1.5} />
            {generate.isPending ? "Generating…" : "Generate tests"}
          </button>
        </div>

        {tests.length === 0 ? (
          <div className="text-[12px] text-neutral-500 border border-dashed border-white/[0.06] rounded-lg p-4 text-center">
            No tests linked. Click "Generate tests" to auto-create them.
          </div>
        ) : (
          <div className="space-y-1.5">
            {tests.map((t) => {
              const tone = TEST_STATUS_TONE[t.status as keyof typeof TEST_STATUS_TONE];
              return (
                <div
                  key={t.id}
                  className="flex items-center gap-2 p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] hover:bg-white/[0.04] transition-colors"
                >
                  <button
                    onClick={() => onSelectTest(t.id, req.id)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <div className="text-[12.5px] text-neutral-200 truncate">{t.name}</div>
                    <div className="flex items-center gap-2 text-[10.5px] font-mono text-neutral-500 mt-0.5">
                      <span>{t.test_type ? TEST_TYPE_LABEL[t.test_type] : "test"}</span>
                      {t.code_language && <span>· {t.code_language}</span>}
                    </div>
                  </button>
                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider",
                        tone?.bg,
                        tone?.text
                      )}
                    >
                      {tone?.label ?? t.status}
                    </span>
                    <button
                      onClick={() => unlink.mutate({ requirement_id: req.id, test_case_id: t.id })}
                      className="text-neutral-600 hover:text-rose-300 transition-colors p-1"
                      title="Unlink test"
                    >
                      <X className="w-3 h-3" strokeWidth={1.5} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="text-[10.5px] font-mono text-neutral-600 space-y-1 pt-2 border-t border-white/[0.04]">
        <div className="flex items-center justify-between">
          <span>id</span>
          <span className="text-neutral-500">{req.id}</span>
        </div>
        {req.created_at && (
          <div className="flex items-center justify-between">
            <span>created</span>
            <span className="text-neutral-500">{new Date(req.created_at).toLocaleString()}</span>
          </div>
        )}
        {req.updated_at && (
          <div className="flex items-center justify-between">
            <span>updated</span>
            <span className="text-neutral-500">{new Date(req.updated_at).toLocaleString()}</span>
          </div>
        )}
      </div>
    </>
  );
}

function TestInspector({
  testId,
  reqId,
  testStatus,
  onSelectRequirement,
}: {
  testId: string;
  reqId: string;
  testStatus: import("./types").TestStatus;
  onSelectRequirement: (reqId: string) => void;
}) {
  const tone = TEST_STATUS_TONE[testStatus];
  return (
    <>
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Beaker className="w-3.5 h-3.5 text-emerald-300" strokeWidth={1.5} />
          <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">Test case</span>
        </div>
        <h2 className="text-[16px] font-semibold text-neutral-100 leading-snug font-mono">{testId}</h2>
        <div className="mt-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10.5px] font-mono uppercase tracking-wider",
              tone?.bg,
              tone?.text
            )}
          >
            <span className={cn("w-1 h-1 rounded-full", tone?.dot)} />
            {tone?.label ?? testStatus}
          </span>
        </div>
      </div>

      <div>
        <div className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider mb-2">Linked to</div>
        <button
          onClick={() => onSelectRequirement(reqId)}
          className="w-full p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] hover:bg-white/[0.04] transition-colors text-left flex items-center gap-2"
        >
          <GitBranch className="w-3.5 h-3.5 text-zinc-300 shrink-0" strokeWidth={1.5} />
          <span className="text-[12.5px] text-neutral-200 flex-1 truncate">{reqId}</span>
          <ExternalLink className="w-3 h-3 text-neutral-600" strokeWidth={1.5} />
        </button>
      </div>

      <div className="text-[12px] text-neutral-500 leading-relaxed">
        Detailed test results live in the Tests page. Use the link above to inspect the parent requirement.
      </div>
    </>
  );
}

function DefectInspector({
  defectId,
  testName,
  reqId,
  onSelectRequirement,
}: {
  defectId: string;
  testName: string | null;
  reqId: string | null;
  onSelectRequirement: (reqId: string) => void;
}) {
  return (
    <>
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Bug className="w-3.5 h-3.5 text-rose-300" strokeWidth={1.5} />
          <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">Defect</span>
        </div>
        <h2 className="text-[16px] font-semibold text-neutral-100 leading-snug font-mono">{defectId}</h2>
        <div className="mt-2">
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10.5px] font-mono uppercase tracking-wider bg-rose-500/15 text-rose-300">
            <span className="w-1 h-1 rounded-full bg-rose-400" />
            Open
          </span>
        </div>
      </div>

      {testName && (
        <div>
          <div className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider mb-2">From test</div>
          <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] text-[12.5px] text-neutral-200 font-mono">
            {testName}
          </div>
        </div>
      )}

      {reqId && (
        <div>
          <div className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider mb-2">Parent requirement</div>
          <button
            onClick={() => onSelectRequirement(reqId)}
            className="w-full p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] hover:bg-white/[0.04] transition-colors text-left flex items-center gap-2"
          >
            <GitBranch className="w-3.5 h-3.5 text-zinc-300 shrink-0" strokeWidth={1.5} />
            <span className="text-[12.5px] text-neutral-200 flex-1 truncate">{reqId}</span>
            <ExternalLink className="w-3 h-3 text-neutral-600" strokeWidth={1.5} />
          </button>
        </div>
      )}
    </>
  );
}

function GapInspector({ reqId }: { reqId: string }) {
  return (
    <>
      <div>
        <div className="flex items-center gap-2 mb-2">
          <AlertCircle className="w-3.5 h-3.5 text-rose-300" strokeWidth={1.5} />
          <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">Coverage gap</span>
        </div>
        <h2 className="text-[16px] font-semibold text-neutral-100 leading-snug">No tests linked</h2>
        <p className="text-[13px] text-neutral-400 leading-relaxed mt-2">
          This requirement has no verified tests. Open the requirement and click <span className="text-emerald-300 font-medium">Generate tests</span> to auto-create them with the LLM.
        </p>
      </div>
      <div className="text-[10.5px] font-mono text-neutral-600">
        <span>requirement</span> <span className="text-neutral-500">{reqId}</span>
      </div>
    </>
  );
}

function Stat({ label, tone, children }: { label: string; tone: string; children: React.ReactNode }) {
  return (
    <div className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
      <div className="text-[10px] font-mono text-neutral-600 uppercase tracking-wider mb-1">{label}</div>
      <div className={cn("text-[13px] font-medium", tone)}>{children}</div>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-10 rounded-lg shimmer-bg" />
      ))}
    </div>
  );
}
