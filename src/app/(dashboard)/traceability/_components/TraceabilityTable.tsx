"use client";

import { motion } from "framer-motion";
import { GitBranch, Beaker, Bug, AlertCircle, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { MatrixRow, Requirement, Defect } from "./types";
import { TEST_STATUS_TONE, REQ_STATUS_TONE, PRIORITY_TONE } from "./constants";

type Row =
  | { kind: "requirement"; data: Requirement; testCount: number; passedCount: number }
  | { kind: "test"; data: { id: string; name: string; status: import("./types").TestStatus; test_type?: string | null }; reqTitle: string; reqId: string }
  | { kind: "defect"; data: Defect };

export function TraceabilityTable({
  rows,
  requirements,
  defects,
  onSelectRequirement,
  onSelectTest,
}: {
  rows: MatrixRow[];
  requirements: Requirement[];
  defects: Defect[];
  onSelectRequirement: (id: string) => void;
  onSelectTest: (id: string) => void;
}) {
  const [filter, setFilter] = useState<"all" | "requirements" | "tests" | "defects">("all");

  const flatRows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    for (const r of rows) {
      const req = requirements.find((x) => x.id === r.requirement_id);
      out.push({
        kind: "requirement",
        data: req ?? { id: r.requirement_id, title: r.title, priority: r.priority, status: "active" },
        testCount: r.test_count,
        passedCount: r.passed_count,
      });
      for (const t of r.tests) {
        out.push({
          kind: "test",
          data: { id: t.id, name: t.name, status: t.status, test_type: t.test_type },
          reqTitle: r.title,
          reqId: r.requirement_id,
        });
      }
    }
    for (const d of defects) {
      out.push({ kind: "defect", data: d });
    }
    return out;
  }, [rows, requirements, defects]);

  const filtered = useMemo(() => {
    if (filter === "all") return flatRows;
    const kindMap: Record<"requirements" | "defects" | "tests", Row["kind"]> = {
      requirements: "requirement",
      tests: "test",
      defects: "defect",
    };
    const target = kindMap[filter];
    return flatRows.filter((r) => r.kind === target);
  }, [filter, flatRows]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow overflow-hidden"
    >
      <div className="flex items-center justify-between p-5 pb-3 gap-3">
        <div>
          <div className="text-[10.5px] font-mono text-neutral-600 uppercase tracking-wider">Flat List</div>
          <h3 className="text-base font-medium text-neutral-100 mt-0.5">
            {flatRows.length} item{flatRows.length === 1 ? "" : "s"}
          </h3>
        </div>
        <div className="flex items-center gap-1 p-0.5 bg-white/[0.03] border border-white/[0.06] rounded-lg">
          {(["all", "requirements", "tests", "defects"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-2.5 py-1 rounded text-[11px] font-medium capitalize transition-colors",
                filter === f ? "bg-white/[0.06] text-neutral-100" : "text-neutral-500 hover:text-neutral-300"
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto max-h-[640px] overflow-y-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr>
              <th className="text-left px-5 py-2.5 text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider border-b border-white/[0.06]">
                Type
              </th>
              <th className="text-left px-3 py-2.5 text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider border-b border-white/[0.06]">
                Name
              </th>
              <th className="text-left px-3 py-2.5 text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider border-b border-white/[0.06]">
                Status
              </th>
              <th className="text-left px-3 py-2.5 text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider border-b border-white/[0.06]">
                Meta
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-5 py-12 text-center text-[12px] text-neutral-500">
                  <Search className="w-4 h-4 mx-auto mb-2 text-neutral-700" strokeWidth={1.5} />
                  No items match the current filter.
                </td>
              </tr>
            ) : (
              filtered.map((row, i) => (
                <motion.tr
                  key={`${row.kind}-${i}`}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.02, 0.4), duration: 0.25 }}
                  className="border-b border-white/[0.04] hover:bg-white/[0.025] transition-colors"
                >
                  <td className="px-5 py-2.5 align-middle">
                    <TypeBadge kind={row.kind} />
                  </td>
                  <td className="px-3 py-2.5 align-middle">
                    {row.kind === "requirement" && (
                      <button
                        onClick={() => onSelectRequirement(row.data.id)}
                        className="text-[13px] text-neutral-200 hover:text-emerald-300 transition-colors text-left"
                      >
                        {row.data.title}
                      </button>
                    )}
                    {row.kind === "test" && (
                      <button
                        onClick={() => onSelectTest(row.data.id)}
                        className="text-left"
                      >
                        <div className="text-[13px] text-neutral-200 hover:text-emerald-300 transition-colors">
                          {row.data.name}
                        </div>
                        <div className="text-[10.5px] font-mono text-neutral-600 mt-0.5">
                          of {row.reqTitle}
                        </div>
                      </button>
                    )}
                    {row.kind === "defect" && (
                      <div className="text-[13px] text-neutral-200 font-mono">
                        {row.data.defect_id}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 align-middle">
                    <StatusCell row={row} />
                  </td>
                  <td className="px-3 py-2.5 align-middle">
                    <MetaCell row={row} />
                  </td>
                </motion.tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}

function TypeBadge({ kind }: { kind: Row["kind"] }) {
  const map = {
    requirement: { icon: GitBranch, label: "req", tone: "indigo" },
    test: { icon: Beaker, label: "test", tone: "emerald" },
    defect: { icon: Bug, label: "defect", tone: "rose" },
  } as const;
  const m = map[kind as keyof typeof map] ?? { icon: AlertCircle, label: "?", tone: "zinc" };
  const Icon = m.icon;
  return (
    <div className="flex items-center gap-1.5">
      <Icon
        className={cn(
          "w-3.5 h-3.5",
          m.tone === "indigo" && "text-zinc-300",
          m.tone === "emerald" && "text-emerald-300",
          m.tone === "rose" && "text-rose-300"
        )}
        strokeWidth={1.5}
      />
      <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">{m.label}</span>
    </div>
  );
}

function StatusCell({ row }: { row: Row }) {
  if (row.kind === "requirement") {
    const tone = REQ_STATUS_TONE[row.data.status];
    return (
      <span className="flex items-center gap-1.5 text-[11px]">
        <span className={cn("w-1.5 h-1.5 rounded-full", tone.dot)} />
        <span className={tone.text}>{tone.label}</span>
      </span>
    );
  }
  if (row.kind === "test") {
    const tone = TEST_STATUS_TONE[row.data.status];
    return (
      <span className="flex items-center gap-1.5 text-[11px]">
        <span className={cn("w-1.5 h-1.5 rounded-full", tone.dot)} />
        <span className={tone.text}>{tone.label}</span>
      </span>
    );
  }
  return <span className="text-[11px] font-mono text-rose-300/80">open</span>;
}

function MetaCell({ row }: { row: Row }) {
  if (row.kind === "requirement") {
    const p = PRIORITY_TONE[row.data.priority];
    return (
      <div className="flex items-center gap-3 text-[10.5px] font-mono">
        <span className="flex items-center gap-1">
          <span className={cn("w-1 h-1 rounded-full", p.dot)} />
          <span className={p.text}>{p.label}</span>
        </span>
        <span className="text-neutral-600">
          {row.passedCount}/{row.testCount} tests
        </span>
      </div>
    );
  }
  if (row.kind === "test") {
    return (
      <span className="text-[10.5px] font-mono text-neutral-500">
        {row.data.test_type ?? "—"}
      </span>
    );
  }
  return (
    <span className="text-[10.5px] font-mono text-neutral-500 truncate max-w-[200px] block">
      {row.data.test_name ?? "—"}
    </span>
  );
}
