"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Compass, ArrowRight, ArrowLeft, Check, FileText, Lightbulb } from "lucide-react";
import type { KGNode, KnowledgeGraph, KGTourStep } from "./types";
import { getNodeTone, NODE_TYPE_LABEL } from "./constants";
import { nodeDisplayName } from "./view-model";
import { cn } from "@/lib/utils";

interface TourPanelProps {
  graph: KnowledgeGraph | null;
  onFocusNode: (nodeId: string) => void;
}

export function TourPanel({ graph, onFocusNode }: TourPanelProps) {
  const steps = graph?.tour ?? [];
  const [currentStep, setCurrentStep] = useState(0);
  const [completed, setCompleted] = useState<Set<number>>(new Set());

  const step = steps[currentStep] ?? null;
  const stepNodes = useMemo(() => {
    if (!step || !graph) return [];
    return step.nodeIds
      .map((id) => graph.nodes.find((n) => n.id === id))
      .filter(Boolean) as KGNode[];
  }, [step, graph]);

  if (!graph || steps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <Compass className="mb-3 h-8 w-8 text-neutral-700" strokeWidth={1.2} />
        <p className="text-[12px] font-medium text-neutral-400">No tour available</p>
        <p className="mt-1 max-w-[260px] text-[10px] leading-5 text-neutral-600">
          This knowledge graph does not include a guided tour. Tours are generated during indexing with a "tour" configuration.
        </p>
      </div>
    );
  }

  function handleNext() {
    if (currentStep < steps.length - 1) {
      setCompleted((prev) => new Set(prev).add(currentStep));
      setCurrentStep((prev) => prev + 1);
    }
  }

  function handlePrev() {
    if (currentStep > 0) {
      setCurrentStep((prev) => prev - 1);
    }
  }

  function handleComplete() {
    setCompleted((prev) => new Set(prev).add(currentStep));
  }

  function jumpTo(index: number) {
    setCurrentStep(index);
  }

  const isLast = currentStep === steps.length - 1;
  const allDone = completed.size >= steps.length;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-white/[0.06] px-1 py-2">
        {steps.map((s, i) => {
          const isActive = i === currentStep;
          const isDone = completed.has(i);
          return (
            <button
              key={s.order}
              type="button"
              onClick={() => jumpTo(i)}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-[8px] font-mono transition-all",
                isActive
                  ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-400/30"
                  : isDone
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-white/[0.04] text-neutral-600 hover:text-neutral-300"
              )}
            >
              {isDone ? <Check className="h-3 w-3" strokeWidth={2} /> : i + 1}
            </button>
          );
        })}
        <div className="ml-auto text-[8px] font-mono text-neutral-600">
          {completed.size}/{steps.length}
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -12 }}
          transition={{ duration: 0.2 }}
          className="flex-1 space-y-4 overflow-y-auto p-1 pt-3"
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/15 text-[9px] font-mono text-emerald-300">
                {currentStep + 1}
              </span>
              <h3 className="text-[13px] font-semibold text-neutral-100">{step?.title}</h3>
            </div>
            <p className="mt-2 text-[11px] leading-6 text-neutral-400">{step?.description}</p>
          </div>

          {step?.languageLesson ? (
            <div className="rounded-2xl border border-amber-400/15 bg-amber-500/8 px-3 py-2.5">
              <div className="flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-[0.2em] text-amber-300">
                <Lightbulb className="h-3 w-3" strokeWidth={1.8} />
                Language lesson
              </div>
              <p className="mt-1.5 text-[11px] leading-6 text-neutral-300">{step.languageLesson}</p>
            </div>
          ) : null}

          {stepNodes.length > 0 ? (
            <div>
              <div className="mb-2 flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-[0.2em] text-neutral-600">
                <FileText className="h-3 w-3" strokeWidth={1.8} />
                Related symbols
              </div>
              <div className="space-y-1">
                {stepNodes.map((node) => {
                  const tone = getNodeTone(node.type);
                  return (
                    <button
                      key={node.id}
                      type="button"
                      onClick={() => onFocusNode(node.id)}
                      className="flex w-full items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-2.5 py-2 text-left transition-colors hover:border-white/[0.09] hover:bg-white/[0.04]"
                    >
                      <span className={cn("h-2 w-2 shrink-0 rounded-full", tone.dot)} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[10px] font-medium text-neutral-100">{nodeDisplayName(node)}</div>
                        <div className="truncate text-[9px] font-mono text-neutral-500">{node.file ?? node.filePath ?? ""}</div>
                      </div>
                      <span className="rounded-md border border-white/[0.06] px-1.5 py-0.5 text-[7px] font-mono uppercase tracking-[0.18em] text-neutral-500">
                        {NODE_TYPE_LABEL[node.type] ?? node.type}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
        </motion.div>
      </AnimatePresence>

      <div className="flex shrink-0 items-center justify-between border-t border-white/[0.06] px-1 py-3">
        <button
          type="button"
          onClick={handlePrev}
          disabled={currentStep === 0}
          className="flex items-center gap-1 rounded-xl border border-white/[0.06] px-3 py-2 text-[10px] text-neutral-400 transition-colors hover:text-neutral-200 disabled:opacity-30"
        >
          <ArrowLeft className="h-3 w-3" strokeWidth={1.8} />
          Back
        </button>

        {isLast ? (
          <button
            type="button"
            onClick={handleComplete}
            className="flex items-center gap-1 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-[10px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/16"
          >
            <Check className="h-3 w-3" strokeWidth={1.8} />
            {allDone ? "Completed" : "Complete"}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleNext}
            className="flex items-center gap-1 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-[10px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/16"
          >
            Next
            <ArrowRight className="h-3 w-3" strokeWidth={1.8} />
          </button>
        )}
      </div>
    </div>
  );
}
