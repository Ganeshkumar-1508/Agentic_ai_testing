"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { TestCaseCard, type TestCaseData } from "@/components/test-cases/TestCaseCard";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown, Beaker, Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TestCaseGroupProps {
  type: string;
  label: string;
  color: string;
  testCases: TestCaseData[];
  onReRun?: (id: string) => void;
  onReRunAll?: (type: string) => void;
  isReRunning?: Record<string, boolean>;
}

// ─── Color classes ────────────────────────────────────────────────────────────

const COLOR_MAP: Record<string, { border: string; bg: string; text: string; badge: string }> = {
  emerald: { border: "border-emerald-500/20", bg: "bg-emerald-500/5", text: "text-emerald-300", badge: "bg-emerald-500/10 text-emerald-300" },
  cyan: { border: "border-zinc-500/20", bg: "bg-zinc-500/5", text: "text-zinc-300", badge: "bg-zinc-500/10 text-zinc-300" },
  violet: { border: "border-zinc-500/20", bg: "bg-zinc-500/5", text: "text-zinc-300", badge: "bg-zinc-500/10 text-zinc-300" },
  amber: { border: "border-amber-500/20", bg: "bg-amber-500/5", text: "text-amber-300", badge: "bg-amber-500/10 text-amber-300" },
  red: { border: "border-red-500/20", bg: "bg-red-500/5", text: "text-red-300", badge: "bg-red-500/10 text-red-300" },
};

// ─── Component ────────────────────────────────────────────────────────────────

export function TestCaseGroup({
  type,
  label,
  color = "emerald",
  testCases,
  onReRun,
  onReRunAll,
  isReRunning,
}: TestCaseGroupProps) {
  const [isOpen, setIsOpen] = useState(true);
  const colors = COLOR_MAP[color] || COLOR_MAP.emerald;

  const passed = testCases.filter((t) => t.status === "passed").length;
  const failed = testCases.filter((t) => t.status === "failed").length;
  const running = testCases.filter((t) => t.status === "running").length;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      {/* Group Header */}
      <div className={cn("border rounded-3xl overflow-hidden", colors.border, colors.bg)}>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="w-full flex items-center gap-3 px-5 py-4 transition-all hover:bg-white/[0.02]"
          >
            <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", colors.badge)}>
              <Beaker className="w-5 h-5" strokeWidth={1.5} />
            </div>

            <div className="flex-1 text-left">
              <h3 className={cn("text-base font-semibold", colors.text)}>
                {label}
              </h3>
              <p className="text-xs text-neutral-500">
                {testCases.length} test{testCases.length !== 1 ? "s" : ""}
              </p>
            </div>

            {/* Stats */}
            <div className="flex items-center gap-3">
              {passed > 0 && (
                <span className="text-xs text-emerald-400 font-medium">{passed} passed</span>
              )}
              {failed > 0 && (
                <span className="text-xs text-red-400 font-medium">{failed} failed</span>
              )}
              {running > 0 && (
                <span className="text-xs text-zinc-400 font-medium flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> {running} running
                </span>
              )}
              {testCases.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    onReRunAll?.(type);
                  }}
                  className="h-8 px-3 rounded-xl text-xs gap-1.5 text-neutral-400 hover:text-emerald-300 hover:bg-emerald-500/10"
                >
                  <Play className="w-3.5 h-3.5" strokeWidth={2} />
                  Run All
                </Button>
              )}
            </div>

            <ChevronDown
              className={cn(
                "w-4 h-4 text-neutral-500 transition-transform",
                isOpen && "rotate-180",
              )}
              strokeWidth={1.5}
            />
          </button>
        </CollapsibleTrigger>

        {/* Cards grid */}
        <CollapsibleContent>
          {testCases.length === 0 ? (
            <div className="px-5 pb-5">
              <p className="text-xs text-neutral-500 text-center py-6">
                No test cases in this group
              </p>
            </div>
          ) : (
            <div className="px-5 pb-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {testCases.map((tc) => (
                  <TestCaseCard
                    key={tc.id}
                    testCase={tc}
                    onReRun={onReRun}
                    isReRunning={isReRunning?.[tc.id]}
                  />
                ))}
              </div>
            </div>
          )}
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
