"use client";

import { motion } from "framer-motion";
import { GitBranch, Beaker, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MatrixRow, TestStatus } from "./types";
import { TEST_STATUS_TONE, PRIORITY_TONE } from "./constants";

function reqCoverageTone(row: MatrixRow): { dot: string; text: string; label: string } {
  if (row.test_count === 0) return { dot: "bg-rose-400", text: "text-rose-300", label: "No coverage" };
  if (row.passed_count === row.test_count) return { dot: "bg-emerald-400", text: "text-emerald-300", label: "Verified" };
  return { dot: "bg-amber-400", text: "text-amber-300", label: "Partial" };
}

export function TraceabilityMatrix({
  rows,
  onSelectRequirement,
  onSelectTest,
}: {
  rows: MatrixRow[];
  onSelectRequirement: (id: string) => void;
  onSelectTest: (id: string) => void;
}) {
  const testsMap = new Map<string, { id: string; name: string; status: TestStatus }>();
  for (const r of rows) {
    for (const t of r.tests) {
      if (!testsMap.has(t.id)) {
        testsMap.set(t.id, { id: t.id, name: t.name, status: t.status });
      }
    }
  }
  const tests = Array.from(testsMap.values());
  const testIds = tests.map((t) => t.id);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow overflow-hidden"
    >
      <div className="flex items-center justify-between p-5 pb-3">
        <div>
          <div className="text-[10.5px] font-mono text-neutral-600 uppercase tracking-wider">Coverage Matrix</div>
          <h3 className="text-base font-medium text-neutral-100 mt-0.5">
            {rows.length} requirement{rows.length === 1 ? "" : "s"} <span className="text-neutral-600">·</span>{" "}
            {tests.length} test{tests.length === 1 ? "" : "s"}
          </h3>
        </div>
        <div className="flex items-center gap-3 text-[10.5px] font-mono text-neutral-500">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="w-3 h-3 text-emerald-400" strokeWidth={1.5} />
            verified
          </span>
          <span className="flex items-center gap-1.5">
            <ShieldAlert className="w-3 h-3 text-amber-400" strokeWidth={1.5} />
            partial
          </span>
          <span className="flex items-center gap-1.5">
            <ShieldQuestion className="w-3 h-3 text-rose-400" strokeWidth={1.5} />
            gap
          </span>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="px-5 pb-8 text-center text-[12px] text-neutral-500">
          No requirements to display. Add one to populate the matrix.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th
                  className="sticky left-0 z-10 bg-surface text-left px-4 py-3 text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider border-b border-white/[0.06] min-w-[280px]"
                >
                  <div className="flex items-center gap-1.5">
                    <GitBranch className="w-3 h-3" strokeWidth={1.5} />
                    Requirement
                  </div>
                </th>
                {tests.map((t) => (
                  <th
                    key={t.id}
                    className="px-3 py-3 text-left text-[10.5px] font-mono text-neutral-500 border-b border-white/[0.06] min-w-[120px] max-w-[180px]"
                  >
                    <div className="flex items-center gap-1.5">
                      <Beaker className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                      <span className="truncate" title={t.name}>
                        {t.name}
                      </span>
                    </div>
                  </th>
                ))}
                <th className="px-4 py-3 text-right text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider border-b border-white/[0.06] min-w-[80px]">
                  Coverage
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const cov = reqCoverageTone(row);
                const linked = new Set(row.tests.map((t) => t.id));
                return (
                  <motion.tr
                    key={row.requirement_id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.05 + i * 0.04, duration: 0.3 }}
                    className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="sticky left-0 z-10 bg-surface px-4 py-3 align-top">
                      <button
                        onClick={() => onSelectRequirement(row.requirement_id)}
                        className="text-left w-full group"
                      >
                        <div className="flex items-center gap-2">
                          {row.priority && (
                            <span
                              className={cn(
                                "w-1.5 h-1.5 rounded-full shrink-0",
                                PRIORITY_TONE[row.priority].dot
                              )}
                            />
                          )}
                          <span className="text-[13px] text-neutral-200 group-hover:text-emerald-300 transition-colors line-clamp-1">
                            {row.title}
                          </span>
                        </div>
                        <div className="text-[10.5px] font-mono text-neutral-600 mt-0.5">
                          {row.requirement_id.slice(0, 12)}
                        </div>
                      </button>
                    </td>
                    {testIds.map((tid) => {
                      const t = row.tests.find((x) => x.id === tid);
                      return (
                        <td key={tid} className="px-3 py-3 align-top">
                          {t ? (
                            <button
                              onClick={() => onSelectTest(t.id)}
                              className="flex items-center gap-1.5 group"
                            >
                              <span
                                className={cn(
                                  "w-2 h-2 rounded-full shrink-0",
                                  TEST_STATUS_TONE[t.status as TestStatus]?.dot ?? "bg-zinc-500"
                                )}
                              />
                              <span className="text-[10.5px] font-mono text-neutral-400 group-hover:text-emerald-300 transition-colors truncate">
                                {t.status}
                              </span>
                            </button>
                          ) : (
                            <span className="block w-2 h-2 rounded-full bg-white/[0.04] mx-auto" />
                          )}
                        </td>
                      );
                    })}
                    <td className="px-4 py-3 text-right align-top">
                      <div className="flex flex-col items-end gap-1">
                        <span className={cn("flex items-center gap-1.5 text-[10.5px] font-mono", cov.text)}>
                          <span className={cn("w-1 h-1 rounded-full", cov.dot)} />
                          {cov.label}
                        </span>
                        <span className="text-[10px] font-mono text-neutral-600">
                          {row.passed_count}/{row.test_count}
                        </span>
                      </div>
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </motion.div>
  );
}
