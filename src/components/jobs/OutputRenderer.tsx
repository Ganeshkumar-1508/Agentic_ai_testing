"use client";

/**
 * OutputRenderer — render a JobOutput as structured cards.
 *
 * The wire shape is FLAT — the backend's ``JobOutput.to_dict()``
 * returns top-level fields (``status``, ``summary``,
 * ``pr_url``, ``cost_usd``, ``duration_s``, ``artifacts``,
 * ``completed_at``). The orchestrator writes the
 * evidence-bundle summary as a JSON-encoded string in
 * ``summary``; we JSON-decode it on demand to read the
 * nested ``test_files`` / ``branch`` / ``pr`` keys.
 *
 * Detected shapes (from the decoded summary):
 *   - `summary.test_files` (string[]) — list of test file paths
 *   - `pr_url` (top-level) — single PR link
 *   - `summary.branch` (string) — branch card
 *   - `artifacts` (top-level) — artifact list
 *   - `cost_usd` / `duration_s` (top-level) — metrics row
 *   - `summary` (top-level) — summary banner
 *
 * The raw JSON is always available (collapsed) so the user
 * can drill into the full payload.
 */
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  GitBranch,
  GitPullRequest,
  FileText,
  Package,
  Clock,
  Coins,
  Hash,
  ChevronDown,
  ChevronRight,
  Link as LinkIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { JobOutput } from "@/lib/types/jobs";

interface OutputRendererProps {
  output: JobOutput;
}

interface DetectedShape {
  hasPr: boolean;
  prUrl?: string;
  hasBranch: boolean;
  branch?: string;
  testFiles: string[];
  artifacts: Array<Record<string, unknown>>;
  costUsd?: number;
  durationS?: number;
  summary?: string;
  rawOutput: Record<string, unknown>;
}

function detectShape(output: JobOutput): DetectedShape {
  // The wire shape is FLAT — read top-level fields directly.
  // The ``summary`` is a JSON-encoded string the orchestrator
  // writes from the evidence-bundle; JSON-decode it for the
  // nested ``test_files`` / ``branch`` keys.
  let summaryObj: Record<string, unknown> = {};
  if (output.summary) {
    try {
      const decoded = JSON.parse(output.summary);
      if (decoded && typeof decoded === "object") {
        summaryObj = decoded as Record<string, unknown>;
      }
    } catch {
      // summary isn't valid JSON — treat it as plain text.
    }
  }

  // PR — top-level ``pr_url`` is the canonical field.
  const hasPr = Boolean(output.pr_url);
  const prUrl = output.pr_url ?? undefined;

  // Branch — read from the decoded summary (legacy locations:
  // ``summary.branch`` / ``summary.target_branch``).
  const branch = (summaryObj.branch ?? summaryObj.target_branch) as
    | string
    | undefined;
  const hasBranch = Boolean(branch);

  // Test files — read from the decoded summary.
  const testFiles = Array.isArray(summaryObj.test_files)
    ? (summaryObj.test_files as string[])
    : Array.isArray(summaryObj.files)
    ? (summaryObj.files as string[])
    : [];

  // Metrics — top-level fields.
  const costUsd = output.cost_usd ?? undefined;
  const durationS = output.duration_s ?? undefined;

  // Summary banner — the raw text, NOT the JSON-decoded
  // object. (We already extracted the structured fields; what
  // we want here is the human-readable summary string.)
  // The decoded object is empty (no recognized structured
  // fields) so we just show the raw ``summary`` text.
  const summary = output.summary && !testFiles.length && !branch
    ? output.summary
    : output.summary || undefined;

  return {
    hasPr,
    prUrl,
    hasBranch,
    branch,
    testFiles,
    artifacts: output.artifacts ?? [],
    costUsd,
    durationS,
    summary,
    rawOutput: { ...output, _summary_decoded: summaryObj },
  };
}

function formatCost(usd: number): string {
  if (usd < 0.01) return `$${(usd * 1000).toFixed(2)}m`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

function formatDuration(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  if (m < 60) return `${m}m${sec}s`;
  const h = Math.floor(m / 60);
  return `${h}h${m % 60}m`;
}

function formatTokens(n: number): string {
  if (n < 1000) return n.toString();
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

export function OutputRenderer({ output }: OutputRendererProps) {
  const shape = detectShape(output);
  const [rawOpen, setRawOpen] = useState(false);

  const hasAnyStructured =
    shape.hasPr ||
    shape.hasBranch ||
    shape.testFiles.length > 0 ||
    shape.artifacts.length > 0 ||
    shape.costUsd !== undefined ||
    shape.durationS !== undefined ||
    shape.summary !== undefined;

  return (
    <div className="space-y-3">
      {shape.summary && (
        <div
          className="rounded-xl px-4 py-3 text-[12px] text-zinc-200"
          style={{ background: "rgba(16,185,129,0.05)", border: "1px solid rgba(16,185,129,0.2)" }}
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
            <span className="font-medium text-emerald-300">Summary</span>
          </div>
          <div className="mt-1.5 text-zinc-300 whitespace-pre-wrap">{shape.summary}</div>
        </div>
      )}

      {(shape.costUsd !== undefined ||
        shape.durationS !== undefined) && (
        <div className="grid grid-cols-2 gap-3">
          {shape.durationS !== undefined && (
            <MetricCard
              icon={Clock}
              label="Duration"
              value={formatDuration(shape.durationS)}
            />
          )}
          {shape.costUsd !== undefined && (
            <MetricCard
              icon={Coins}
              label="Cost"
              value={formatCost(shape.costUsd)}
            />
          )}
        </div>
      )}

      {shape.hasPr && shape.prUrl && (
        <Card title="Pull Request" icon={GitPullRequest} accent="emerald">
          <a
            href={shape.prUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-[12px] text-emerald-300 hover:text-emerald-200 font-mono"
          >
            <LinkIcon className="w-3 h-3" strokeWidth={1.5} />
            PR
          </a>
          <div className="text-[10px] text-zinc-500 font-mono mt-1 break-all">
            {shape.prUrl}
          </div>
        </Card>
      )}

      {shape.hasBranch && (
        <Card title="Branch" icon={GitBranch} accent="blue">
          {shape.branch && (
            <div className="text-[12px] text-zinc-200 font-mono">{shape.branch}</div>
          )}
        </Card>
      )}

      {shape.testFiles.length > 0 && (
        <Card
          title={`Test Files (${shape.testFiles.length})`}
          icon={FileText}
          accent="violet"
        >
          <ul className="space-y-1">
            {shape.testFiles.slice(0, 10).map((f) => (
              <li
                key={f}
                className="text-[11px] text-zinc-300 font-mono truncate"
                title={f}
              >
                <FileText className="w-3 h-3 inline-block mr-1.5 text-zinc-600" strokeWidth={1.5} />
                {f}
              </li>
            ))}
            {shape.testFiles.length > 10 && (
              <li className="text-[10px] text-zinc-600 font-mono">
                + {shape.testFiles.length - 10} more
              </li>
            )}
          </ul>
        </Card>
      )}

      {shape.artifacts.length > 0 && (
        <Card
          title={`Artifacts (${shape.artifacts.length})`}
          icon={Package}
          accent="amber"
        >
          <ul className="space-y-1">
            {shape.artifacts.map((a, idx) => {
              const id = String(a.id ?? a.path ?? a.url ?? idx);
              const kind = String(a.kind ?? a.type ?? "artifact");
              const url = typeof a.url === "string" ? a.url : null;
              return (
                <li key={id} className="flex items-center gap-2 text-[11px]">
                  <span className="text-[10px] font-mono px-1 py-0.5 rounded bg-white/[0.04] text-zinc-400">
                    {kind}
                  </span>
                  {url ? (
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-zinc-300 font-mono hover:text-amber-300 truncate"
                    >
                      {id}
                    </a>
                  ) : (
                    <span className="text-zinc-300 font-mono truncate">{id}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {!hasAnyStructured && (
        <div className="text-sm text-zinc-500">
          Output captured but no recognized structured fields.
        </div>
      )}

      <button
        type="button"
        onClick={() => setRawOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 text-[10px] font-mono text-zinc-600 hover:text-zinc-400 transition-colors"
      >
        {rawOpen ? (
          <ChevronDown className="w-3 h-3" strokeWidth={1.5} />
        ) : (
          <ChevronRight className="w-3 h-3" strokeWidth={1.5} />
        )}
        {rawOpen ? "Hide" : "Show"} raw JSON
      </button>
      <AnimatePresence>
        {rawOpen && (
          <motion.pre
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="text-[11px] text-zinc-300 font-mono bg-zinc-950/40 rounded-xl p-3 overflow-x-auto max-h-96"
          >
            {JSON.stringify(shape.rawOutput, null, 2)}
          </motion.pre>
        )}
      </AnimatePresence>
    </div>
  );
}

function Card({
  title,
  icon: Icon,
  children,
  accent,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  children: React.ReactNode;
  accent: "emerald" | "blue" | "violet" | "amber";
}) {
  const accentCls: Record<typeof accent, string> = {
    emerald: "text-emerald-400",
    blue: "text-emerald-400/80",
    violet: "text-emerald-400/60",
    amber: "text-amber-400",
  };
  return (
    <div
      className="rounded-xl p-4"
      style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className={cn("w-3.5 h-3.5", accentCls[accent])} strokeWidth={1.5} />
        <span className="text-[11px] font-semibold text-zinc-300 tracking-tight uppercase">
          {title}
        </span>
      </div>
      <div>{children}</div>
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div
      className="rounded-xl p-3"
      style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <div className="flex items-center gap-1.5 text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
        <Icon className="w-3 h-3" strokeWidth={1.5} />
        {label}
      </div>
      <div className="mt-1 text-[18px] font-mono text-zinc-100 tabular-nums">{value}</div>
      {sub && <div className="text-[10px] text-zinc-600 font-mono mt-0.5">{sub}</div>}
    </div>
  );
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}
