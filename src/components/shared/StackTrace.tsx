"use client";

import { useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, Copy, Check, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface StackFrame {
  file: string;
  line: number | null;
  column: number | null;
  function: string;
  isInternal: boolean;
  raw: string;
  code?: string;
}

interface ParsedTrace {
  errorType: string | null;
  message: string | null;
  frames: StackFrame[];
  raw: string;
}

function parsePythonTrace(raw: string): ParsedTrace {
  const lines = raw.trim().split("\n");
  const frames: StackFrame[] = [];
  let errorType: string | null = null;
  let message: string | null = null;

  const frameRegex = /^\s*File\s+"([^"]+)".*?line\s+(\d+)(?:,\s+in\s+(.+))?$/;
  const codeRegex = /^\s+(.+)$/;
  const errorRegex = /^(\w+(?:\.\w+)*):\s*(.*)$/;

  let latestCode = "";

  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    if (line.includes("Traceback")) continue;

    const frameMatch = line.match(frameRegex);
    if (frameMatch) {
      latestCode = "";
      const nextLine = lines[li + 1];
      if (nextLine && nextLine.match(codeRegex)) {
        latestCode = nextLine.trim();
      }
      frames.push({
        file: frameMatch[1],
        line: parseInt(frameMatch[2], 10) || null,
        column: null,
        function: frameMatch[3] || "<module>",
        isInternal: /(site-packages|node_modules|dist\/|\.venv|env\/)/.test(frameMatch[1]),
        raw: line,
        code: latestCode || undefined,
      });
      continue;
    }

    const errorMatch = line.match(errorRegex);
    if (errorMatch && frames.length > 0) {
      errorType = errorMatch[1];
      message = errorMatch[2];
    }
  }

  if (!errorType && frames.length > 0) {
    const last = lines[lines.length - 1];
    if (last && !last.match(frameRegex) && !last.includes("Traceback")) {
      const err = last.match(errorRegex);
      if (err) {
        errorType = err[1];
        message = err[2];
      } else {
        message = last.trim();
      }
    }
  }

  return { errorType, message, frames, raw };
}

function parseJsTrace(raw: string): ParsedTrace {
  const lines = raw.trim().split("\n");
  const frames: StackFrame[] = [];
  let errorType: string | null = "Error";
  let message: string | null = null;

  const topMatch = lines[0]?.match(/^(\w+Error|Error|TypeError|ReferenceError|SyntaxError|RangeError|URIError|EvalError|AggregateError):\s*(.*)$/);
  if (topMatch) {
    errorType = topMatch[1];
    message = topMatch[2] || null;
  } else {
    message = lines[0] || null;
  }

  const frameRegex = /^\s+at\s+(?:(.+?)\s+\()?(?:(.+?):(\d+)(?::(\d+))?)\)?$/;
  for (let li = 1; li < lines.length; li++) {
    const line = lines[li].trim();
    if (!line || line.startsWith("at ")) {
      const m = lines[li].match(frameRegex);
      if (m) {
        frames.push({
          file: m[2] || "unknown",
          line: parseInt(m[3], 10) || null,
          column: m[4] ? parseInt(m[4], 10) : null,
          function: m[1] || "<anonymous>",
          isInternal: /(node_modules|webpack:\/\/|\(internal)/.test(lines[li]),
          raw: lines[li].trim(),
        });
      } else {
        frames.push({
          file: "unknown",
          line: null,
          column: null,
          function: lines[li].replace(/^at\s+/, "").trim(),
          isInternal: false,
          raw: lines[li].trim(),
        });
      }
    }
  }

  return { errorType, message, frames, raw };
}

function parseTrace(raw: string): ParsedTrace {
  if (!raw) return { errorType: null, message: null, frames: [], raw };
  if (raw.includes("Traceback (most recent call last)")) {
    return parsePythonTrace(raw);
  }
  if (/^\w*(Error|TypeError|ReferenceError|SyntaxError|RangeError|URIError)\b/.test(raw.trim()) || raw.includes("    at ")) {
    return parseJsTrace(raw);
  }
  return { errorType: null, message: raw, frames: [], raw };
}

export function StackTrace({ trace, defaultOpen = false }: { trace: string; defaultOpen?: boolean }) {
  const parsed = useMemo(() => parseTrace(trace), [trace]);
  const [open, setOpen] = useState<boolean>(defaultOpen || true);
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(trace);
    setCopied(true);
    toast.success("Stack trace copied");
    setTimeout(() => setCopied(false), 1500);
  }, [trace]);

  if (!trace) return null;

  return (
    <div className="border border-red-500/15 rounded-3xl bg-red-500/[0.03] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full px-4 py-3 text-left transition-colors hover:bg-red-500/[0.03] active:scale-[0.999]"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-6 h-6 rounded-lg bg-red-500/10 flex items-center justify-center shrink-0">
            <AlertTriangle size={12} className="text-red-400" strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            {parsed.errorType ? (
              <span className="text-xs font-semibold tracking-tight text-red-400">
                {parsed.errorType}
                {parsed.message ? <span className="text-red-400/70 font-normal">: {parsed.message}</span> : null}
              </span>
            ) : (
              <span className="text-xs font-semibold tracking-tight text-red-400">Error</span>
            )}
            {parsed.frames.length > 0 && (
              <span className="text-[10px] text-red-400/50 ml-2 font-mono tabular-nums">
                {parsed.frames.length} frame{parsed.frames.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); handleCopy(); }}
            className="p-1.5 rounded-lg text-red-400/50 hover:text-red-400 hover:bg-red-500/10 transition-all active:scale-[0.93]"
            title="Copy raw trace"
          >
            {copied ? <Check size={11} strokeWidth={1.5} /> : <Copy size={11} strokeWidth={1.5} />}
          </button>
          {open ? (
            <ChevronDown size={12} className="text-red-400/50" strokeWidth={1.5} />
          ) : (
            <ChevronRight size={12} className="text-red-400/50" strokeWidth={1.5} />
          )}
        </div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 100, damping: 20, mass: 0.8 }}
            className="overflow-hidden"
          >
            <div className="border-t border-red-500/10 mx-4" />
            <div className="px-4 pb-3.5 pt-2.5 space-y-0.5">
              {parsed.frames.length > 0 ? (
                parsed.frames.map((frame, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex items-start gap-2.5 py-1 text-[11px] font-mono leading-relaxed",
                      frame.isInternal ? "opacity-30" : "text-red-400/70",
                    )}
                  >
                    <span className="text-red-400/30 shrink-0 mt-0.5 tabular-nums w-5 text-right">#{parsed.frames.length - i}</span>
                    <div className="min-w-0 flex-1">
                      <span className={cn("font-medium", frame.isInternal ? "text-red-300/30" : "text-red-300/70")}>{frame.function}</span>
                      <span className="text-red-400/30 mx-1">at</span>
                      <span className="text-red-400/50">{frame.file}</span>
                      {frame.line && (
                        <span className="text-red-400/30">
                          :{frame.line}{frame.column ? `:${frame.column}` : ""}
                        </span>
                      )}
                      {frame.code && (
                        <div className="text-[10px] text-red-400/25 mt-0.5 pl-3 border-l border-red-500/15 leading-relaxed">{frame.code}</div>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-[11px] text-red-400/60 font-mono leading-relaxed whitespace-pre-wrap break-all">
                  {trace}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
