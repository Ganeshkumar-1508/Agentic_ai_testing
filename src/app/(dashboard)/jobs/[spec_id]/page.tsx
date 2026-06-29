"use client";

/**
 * /jobs/[spec_id] — full JobSpec detail with control surface.
 *
 * Uses the C08 Q6/Q8 endpoints:
 *   - GET    /api/jobs/{spec_id}            (full spec + comments)
 *   - POST   /api/jobs/{spec_id}/cancel
 *   - POST   /api/jobs/{spec_id}/pause
 *   - POST   /api/jobs/{spec_id}/resume
 *   - POST   /api/jobs/{spec_id}/comments   (add comment)
 *   - GET    /api/jobs/{spec_id}/output     (only when completed)
 *
 * Plus the per-job live activity feed (C01-C08 events filtered
 * by ``payload.spec_id``).
 */

import { Suspense, useState, useRef, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  Pause,
  Play,
  StopCircle,
  Send,
  Briefcase,
  GitBranch,
  Tag,
  Activity as ActivityIcon,
  FileOutput,
  AlertTriangle,
  RefreshCw,
  Hash,
  User,
  Calendar,
} from "lucide-react";
import { api } from "@/lib/api/api-client";
import type { JobSpec, JobComment, JobOutput } from "@/lib/types/jobs";
import { PageShell } from "@/components/shared/PageShell";
import { ActivityFeed } from "@/components/activity/ActivityFeed";
import { OutputRenderer } from "@/components/jobs/OutputRenderer";
import { ThrottleIndicator } from "@/components/jobs/ThrottleIndicator";
import { useThrottleState } from "@/lib/hooks/use-throttle-state";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const STATUS_PILL: Record<string, string> = {
  queued: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  submitted: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  running: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
  cancelled: "bg-red-500/10 text-red-400 border-red-500/20",
  paused: "bg-amber-500/10 text-amber-400 border-amber-500/20",
};

const TIER_LABEL: Record<number, string> = {
  1: "Autonomous",
  2: "Supervised",
  3: "Human",
};

function ThrottleSection({ specId, sessionId }: { specId: string; sessionId: string | null }) {
  const throttle = useThrottleState({ sessionId, specId });
  return (
    <div
      className="rounded-[2rem] p-6"
      style={{ background: "#0e0e18" }}
    >
      <ThrottleIndicator state={throttle} />
    </div>
  );
}

function JobDetailInner() {
  const router = useRouter();
  const params = useParams<{ spec_id: string }>();
  const specId = params?.spec_id || "";
  const qc = useQueryClient();

  const { data: spec, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ["job", specId],
    queryFn: () => api.get<JobSpec>(`/api/jobs/${encodeURIComponent(specId)}`),
    refetchInterval: (q) => {
      const data = q.state.data as JobSpec | undefined;
      if (!data) return 3000;
      if (data.status === "running" || data.status === "submitted" || data.status === "queued") return 2000;
      return 15000;
    },
  });

  const { data: output, isLoading: isOutputLoading } = useQuery({
    queryKey: ["job-output", specId],
    queryFn: () => api.get<JobOutput>(`/api/jobs/${encodeURIComponent(specId)}/output`),
    enabled: !!spec && (spec.status === "completed" || spec.status === "failed" || spec.status === "cancelled"),
    retry: false,
  });

  const cancel = useMutation({
    mutationFn: () => api.post<{ spec_id: string; cancelled: boolean }>(`/api/jobs/${encodeURIComponent(specId)}/cancel`),
    onSuccess: (r) => {
      if (r.cancelled) toast.success("Job cancelled");
      else toast.error("Job could not be cancelled (already terminal)");
      qc.invalidateQueries({ queryKey: ["job", specId] });
    },
    onError: (e: Error) => toast.error(`Cancel failed: ${e.message}`),
  });

  const pause = useMutation({
    mutationFn: () => api.post<{ spec_id: string; paused: boolean }>(`/api/jobs/${encodeURIComponent(specId)}/pause`),
    onSuccess: (r) => {
      if (r.paused) toast.success("Job paused");
      else toast.error("Job could not be paused (already terminal)");
      qc.invalidateQueries({ queryKey: ["job", specId] });
    },
    onError: (e: Error) => toast.error(`Pause failed: ${e.message}`),
  });

  const resume = useMutation({
    mutationFn: () => api.post<{ spec_id: string; resumed: boolean }>(`/api/jobs/${encodeURIComponent(specId)}/resume`),
    onSuccess: (r) => {
      if (r.resumed) toast.success("Job resumed");
      else toast.error("Job could not be resumed");
      qc.invalidateQueries({ queryKey: ["job", specId] });
    },
    onError: (e: Error) => toast.error(`Resume failed: ${e.message}`),
  });

  if (isLoading) {
    return <div className="text-sm text-zinc-500">Loading job {specId}…</div>;
  }
  if (error || !spec) {
    return (
      <PageShell
        title="Job not found"
        description={`spec_id: ${specId}`}
        sections={[
          {
            title: "Error",
            children: (
              <div className="rounded-[2rem] p-6 text-sm text-red-400" style={{ background: "#0e0e18" }}>
                {(error as Error)?.message || "This job does not exist or has been deleted."}
              </div>
            ),
          },
        ]}
      />
    );
  }

  const isActive = spec.status === "running" || spec.status === "submitted" || spec.status === "queued";
  const isPaused = spec.status === "paused";
  const isTerminal = spec.status === "completed" || spec.status === "failed" || spec.status === "cancelled";

  return (
    <PageShell
      title={truncate(spec.prompt, 80) || "Job"}
      description={`spec_id: ${spec.spec_id} · tier ${spec.tier} (${TIER_LABEL[spec.tier]})`}
      actions={
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push("/jobs")}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-zinc-800/50 bg-zinc-900/60 text-[12px] text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" strokeWidth={1.5} />
            All jobs
          </button>
          <button
            onClick={() => refetch()}
            className="p-1.5 rounded-lg border border-zinc-800/50 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Refresh"
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5", isRefetching && "animate-spin")}
              strokeWidth={1.5}
            />
          </button>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-[10px] font-mono px-2 py-1 rounded-full border tabular-nums",
              STATUS_PILL[spec.status] || STATUS_PILL.queued,
            )}
          >
            {(spec.status === "running" || spec.status === "submitted" || spec.status === "queued") && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            )}
            {spec.status}
          </span>
          <div className="flex items-center gap-1.5">
            <ControlButton
              onClick={() => pause.mutate()}
              disabled={!isActive || pause.isPending}
              title="Pause"
              tone="warn"
            >
              <Pause className="w-3.5 h-3.5" strokeWidth={1.5} />
              Pause
            </ControlButton>
            <ControlButton
              onClick={() => resume.mutate()}
              disabled={!isPaused || resume.isPending}
              title="Resume"
              tone="info"
            >
              <Play className="w-3.5 h-3.5" strokeWidth={1.5} />
              Resume
            </ControlButton>
            <ControlButton
              onClick={() => cancel.mutate()}
              disabled={isTerminal || cancel.isPending}
              title="Cancel"
              tone="danger"
            >
              <StopCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
              Cancel
            </ControlButton>
          </div>
        </div>
      }
      sections={[
        {
          title: "Spec",
          description: "Immutable fields the user submitted with this job.",
          children: (
            <div
              className="rounded-[2rem] p-6 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4"
              style={{ background: "#0e0e18" }}
            >
              <SpecField icon={Tag} label="Source" value={spec.source || "api"} mono />
              <SpecField icon={Hash} label="Run id" value={spec.run_id || "—"} mono />
              <SpecField
                icon={GitBranch}
                label="Repository"
                value={spec.repo_url || "—"}
                mono
                className="md:col-span-2"
              />
              <SpecField icon={GitBranch} label="Branch" value={spec.branch || "main"} mono />
              <SpecField icon={Hash} label="SHA" value={spec.sha || "—"} mono />
              <div className="md:col-span-2">
                <SpecField icon={Briefcase} label="Prompt" value={spec.prompt} />
              </div>
              <div className="md:col-span-2 flex items-start gap-3">
                <FieldIcon><Tag className="w-3 h-3" strokeWidth={1.5} /></FieldIcon>
                <div className="flex-1">
                  <div className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">
                    Capabilities
                  </div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {spec.capabilities.length === 0 ? (
                      <span className="text-[12px] text-zinc-600 font-mono">none</span>
                    ) : (
                      spec.capabilities.map((c) => (
                        <span
                          key={c}
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-300"
                        >
                          {c}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </div>
              {Object.keys(spec.context).length > 0 && (
                <div className="md:col-span-2">
                  <div className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">
                    Context
                  </div>
                  <pre className="text-[11px] text-zinc-300 font-mono bg-zinc-950/40 rounded-xl p-3 overflow-x-auto max-h-48">
                    {JSON.stringify(spec.context, null, 2)}
                  </pre>
                </div>
              )}
              {spec.error && (
                <div className="md:col-span-2">
                  <div className="text-[10px] font-medium text-red-400 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                    <AlertTriangle className="w-3 h-3" strokeWidth={2} />
                    Error
                  </div>
                  <pre className="text-[11px] text-red-300 font-mono bg-red-500/[0.04] rounded-xl p-3 overflow-x-auto">
                    {spec.error}
                  </pre>
                </div>
              )}
            </div>
          ),
        },
        {
          title: "Lifecycle",
          description: "Creation, start, completion timestamps.",
          children: (
            <div
              className="rounded-[2rem] p-6 grid grid-cols-2 md:grid-cols-4 gap-4"
              style={{ background: "#0e0e18" }}
            >
              <Timestamp icon={Calendar} label="Created" iso={spec.created_at} />
              <Timestamp icon={ActivityIcon} label="Started" iso={spec.started_at} />
              <Timestamp icon={ActivityIcon} label="Completed" iso={spec.completed_at} />
              <div className="flex flex-col gap-1.5">
                <div className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
                  Duration
                </div>
                <div className="text-[18px] font-mono text-zinc-100 tabular-nums">
                  {formatDuration(
                    spec.started_at && spec.completed_at
                      ? (new Date(spec.completed_at).getTime() - new Date(spec.started_at).getTime()) / 1000
                      : null,
                  )}
                </div>
              </div>
            </div>
          ),
        },
        {
          title: "Throttle",
          description: "C07 budget-throttle ladder. Climbs automatically as the run's spend crosses the configured thresholds.",
          children: (
            <ThrottleSection
              specId={spec.spec_id}
              sessionId={typeof spec.context?.session_id === "string" ? spec.context.session_id : null}
            />
          ),
        },
        ...(isTerminal
          ? [
              {
                title: "Output",
                description: "What the orchestrator produced for this job.",
                children: (
                  <div
                    className="rounded-[2rem] p-6"
                    style={{ background: "#0e0e18" }}
                  >
                    {isOutputLoading ? (
                      <div className="text-sm text-zinc-500">Loading output…</div>
                    ) : output ? (
                      <OutputRenderer output={output} />
                    ) : (
                      <div className="text-sm text-zinc-500">
                        No output captured for this job.
                      </div>
                    )}
                  </div>
                ),
              },
            ]
          : []),
        {
          title: "Live activity",
          description: "C01-C08 events for this job, surfaced as they happen.",
          children: (
            <ActivityFeed
              sessionId={typeof spec.context?.session_id === "string" ? spec.context.session_id : null}
              payloadMatch={{ key: "spec_id", value: spec.spec_id }}
              title={`Activity for ${truncate(spec.spec_id, 16)}`}
              compact
              hideFilters
              emptyMessage="No activity yet for this job."
            />
          ),
        },
        {
          title: "Comments",
          description: "User notes attached to this job. Use the box below to add one.",
          children: (
            <CommentsSection specId={spec.spec_id} initialComments={spec.comments || []} />
          ),
        },
      ]}
    />
  );
}

function CommentsSection({
  specId,
  initialComments,
}: {
  specId: string;
  initialComments: JobComment[];
}) {
  const qc = useQueryClient();
  const [body, setBody] = useState("");
  const [author, setAuthor] = useState("user");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const add = useMutation({
    mutationFn: () =>
      api.post<JobComment>(`/api/jobs/${encodeURIComponent(specId)}/comments`, {
        author,
        body,
        kind: "comment",
      }),
    onSuccess: () => {
      setBody("");
      inputRef.current?.focus();
      qc.invalidateQueries({ queryKey: ["job", specId] });
    },
    onError: (e: Error) => toast.error(`Add comment failed: ${e.message}`),
  });

  return (
    <div
      className="rounded-[2rem] p-6 flex flex-col gap-4"
      style={{ background: "#0e0e18" }}
    >
      <div className="space-y-2">
        <AnimatePresence initial={false}>
          {initialComments.length === 0 ? (
            <div className="text-sm text-zinc-500 text-center py-4">
              No comments yet.
            </div>
          ) : (
            initialComments.map((c) => (
              <motion.div
                key={c.comment_id}
                layout
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                className="flex items-start gap-2.5 px-3 py-2.5 rounded-xl bg-white/[0.02]"
              >
                <div className="w-6 h-6 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
                  <User className="w-3 h-3 text-emerald-400" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-500">
                    <span className="text-zinc-300">{c.author}</span>
                    <span>·</span>
                    <span>{formatTimeAgo(c.created_at)}</span>
                    {c.kind !== "comment" && (
                      <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">
                        {c.kind}
                      </span>
                    )}
                  </div>
                  <div className="text-[12px] text-zinc-200 mt-1 whitespace-pre-wrap break-words">
                    {c.body}
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
      <div className="flex items-start gap-2">
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-zinc-800/50 bg-zinc-900/60 shrink-0">
          <User className="w-3 h-3 text-zinc-500" strokeWidth={1.5} />
          <input
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            className="bg-transparent text-[12px] text-zinc-200 placeholder-zinc-600 outline-none w-20 font-mono"
            placeholder="author"
          />
        </div>
        <textarea
          ref={inputRef}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              if (body.trim()) add.mutate();
            }
          }}
          rows={2}
          placeholder="Add a comment… (⌘+Enter to send)"
          className="flex-1 px-3 py-2 rounded-lg border border-zinc-800/50 bg-zinc-900/60 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none resize-none focus:border-emerald-500/30 font-mono"
        />
        <button
          onClick={() => body.trim() && add.mutate()}
          disabled={!body.trim() || add.isPending}
          className={cn(
            "p-2 rounded-lg transition-colors shrink-0",
            body.trim() && !add.isPending
              ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/15"
              : "bg-zinc-800/40 border border-zinc-800/50 text-zinc-600",
          )}
          title="Send comment"
        >
          <Send className="w-3.5 h-3.5" strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}

function SpecField({
  icon: Icon,
  label,
  value,
  mono,
  className,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start gap-3", className)}>
      <FieldIcon>
        <Icon className="w-3 h-3" strokeWidth={1.5} />
      </FieldIcon>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">
          {label}
        </div>
        <div
          className={cn(
            "text-[12px] text-zinc-200 break-words",
            mono && "font-mono",
          )}
        >
          {value}
        </div>
      </div>
    </div>
  );
}

function FieldIcon({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-6 h-6 rounded-md bg-white/[0.04] flex items-center justify-center text-zinc-500 shrink-0 mt-0.5">
      {children}
    </div>
  );
}

function Timestamp({
  icon: Icon,
  label,
  iso,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  iso: string | null;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
        <Icon className="w-3 h-3" strokeWidth={1.5} />
        {label}
      </div>
      <div className="text-[12px] font-mono text-zinc-200 tabular-nums">
        {iso ? new Date(iso).toLocaleString() : "—"}
      </div>
    </div>
  );
}

function ControlButton({
  onClick,
  disabled,
  title,
  tone,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  title: string;
  tone: "warn" | "danger" | "info";
  children: React.ReactNode;
}) {
  const toneCls: Record<typeof tone, string> = {
    warn: "border-amber-500/20 text-amber-300 hover:bg-amber-500/10",
    danger: "border-red-500/20 text-red-300 hover:bg-red-500/10",
    info: "border-emerald-500/20 text-emerald-300 hover:bg-emerald-500/10",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[12px] font-medium transition-colors",
        toneCls[tone],
        disabled && "opacity-30 cursor-not-allowed",
      )}
    >
      {children}
    </button>
  );
}

function formatDuration(raw: number | null): string {
  if (raw == null) return "—";
  if (raw < 60) return `${raw.toFixed(1)}s`;
  const m = Math.floor(raw / 60);
  const s = Math.floor(raw % 60);
  if (m < 60) return `${m}m${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h${m % 60}m`;
}

function formatTimeAgo(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return iso;
  const sec = Math.floor((Date.now() - d) / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

function truncate(s: string, n: number): string {
  if (!s) return "";
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

export default function JobDetailPage() {
  return (
    <Suspense fallback={<div className="text-zinc-500">Loading…</div>}>
      <JobDetailInner />
    </Suspense>
  );
}
