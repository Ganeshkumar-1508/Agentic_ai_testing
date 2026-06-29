"use client";

import { usePipelineStore } from "@/stores/pipeline-store";
import { CheckCircle2, XCircle } from "lucide-react";

export function SandboxTestSummary() {
  const { events } = usePipelineStore();

  const toolResults = events.filter((e) => e.type === "tool_result" || e.type === "ToolExecutionCompleted");
  const testNames: { name: string; status: "pass" | "fail"; duration?: number }[] = [];

  for (const ev of toolResults) {
    if (ev.type === "ToolExecutionCompleted" && ev.tool_name === "test_executor") {
      try {
        const parsed = JSON.parse(ev.output_preview || "{}");
        const tests = parsed.tests || [];
        for (const t of tests) {
          if (!testNames.find((tn) => tn.name === t.name)) {
            testNames.push({ name: t.name, status: t.status === "passed" ? "pass" : "fail", duration: t.duration });
          }
        }
      } catch {
        const lines = (ev.output_preview || "").split("\n");
        for (const line of lines) {
          const m = line.match(/(PASS|FAIL)\s+(.+?)\s+\((\d+)ms\)/);
          if (m && !testNames.find((tn) => tn.name === m[2])) {
            testNames.push({ name: m[2], status: m[1] === "PASS" ? "pass" : "fail", duration: parseInt(m[3]) });
          }
        }
      }
    }
  }

  const passed = testNames.filter((t) => t.status === "pass").length;
  const failed = testNames.filter((t) => t.status === "fail").length;
  const maxDur = Math.max(...testNames.map((t) => t.duration || 0), 1);

  if (testNames.length === 0) return null;

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5">
      <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider mb-3">Results</div>
      <div className="flex items-center gap-4 mb-3 pb-3 border-b border-white/[0.04]">
        <div className="flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />
          <span className="text-sm font-medium text-emerald-400 tabular-nums">{passed}</span>
          <span className="text-[11px] text-neutral-500">passed</span>
        </div>
        <div className="flex items-center gap-1.5">
          <XCircle className="w-3.5 h-3.5 text-red-400" strokeWidth={2} />
          <span className="text-sm font-medium text-red-400 tabular-nums">{failed}</span>
          <span className="text-[11px] text-neutral-500">failed</span>
        </div>
      </div>
      <div className="space-y-1.5">
        {testNames.map((t) => (
          <div key={t.name} className="flex items-center gap-2 text-xs">
            {t.status === "pass" ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" strokeWidth={2} />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" strokeWidth={2} />
            )}
            <span className="text-neutral-400 truncate flex-1">{t.name}</span>
            <div className="w-16 h-1 bg-white/[0.04] rounded-full overflow-hidden shrink-0">
              <div
                className="h-full rounded-full"
                style={{ width: `${((t.duration || 0) / maxDur) * 100}%`, background: t.status === "pass" ? "#34d399" : "#f87171" }}
              />
            </div>
            <span className="text-neutral-600 font-mono text-[10px] tabular-nums w-10 text-right">{t.duration || 0}ms</span>
          </div>
        ))}
      </div>
    </div>
  );
}
