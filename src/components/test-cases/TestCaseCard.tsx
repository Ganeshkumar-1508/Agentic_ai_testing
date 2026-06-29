"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  TestTube,
  Code,
  ChevronDown,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
  FileText,
  Trash2,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TestCaseData {
  id: string;
  name: string;
  type: string;
  status: string;
  code?: string | null;
  codeLanguage?: string | null;
  description?: string | null;
  createdAt: string;
  priority?: string;
  duration?: number | null;
  errorMessage?: string | null;
}

export interface TestCaseCardProps {
  key?: string;
  testCase: TestCaseData;
  onReRun?: (id: string) => void;
  onDelete?: (id: string) => void;
  isReRunning?: boolean;
}

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle; label: string; className: string }> = {
  passed: { icon: CheckCircle, label: "Passed", className: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" },
  failed: { icon: XCircle, label: "Failed", className: "text-red-400 bg-red-500/10 border-red-500/20" },
  pending: { icon: Clock, label: "Pending", className: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
  running: { icon: Loader2, label: "Running", className: "text-zinc-400 bg-zinc-500/10 border-zinc-500/20" },
};

const DEFAULT_STATUS = { icon: Clock, label: "Unknown", className: "text-neutral-400 bg-white/[0.03] border-white/[0.08]" };

function getStatusConfig(status: string) {
  return STATUS_CONFIG[status.toLowerCase()] || DEFAULT_STATUS;
}

// ─── Type config ──────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<string, { label: string; className: string }> = {
  unit: { label: "Unit", className: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20" },
  api: { label: "Integration", className: "bg-zinc-500/10 text-zinc-300 border-zinc-500/20" },
  ui: { label: "E2E", className: "bg-zinc-500/10 text-zinc-300 border-zinc-500/20" },
  performance: { label: "Performance", className: "bg-amber-500/10 text-amber-300 border-amber-500/20" },
  security: { label: "Security", className: "bg-red-500/10 text-red-300 border-red-500/20" },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type.toLowerCase()] || { label: type, className: "bg-white/[0.05] text-neutral-300 border-white/[0.08]" };
}

function formatDate(dateStr: string) {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function TestCaseCard({ testCase, onReRun, onDelete, isReRunning }: TestCaseCardProps) {
  const [codeOpen, setCodeOpen] = useState(false);
  const StatusIcon = getStatusConfig(testCase.status).icon;
  const typeCfg = getTypeConfig(testCase.type);
  const statusCfg = getStatusConfig(testCase.status);
  const hasCode = !!testCase.code || !!testCase.codeLanguage;

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl overflow-hidden transition-all hover:border-white/[0.1]">
      {/* Card Header */}
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center shrink-0", typeCfg.className)}>
            <TestTube className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-neutral-100 leading-tight whitespace-normal break-words">
              {testCase.name}
            </h3>
            {testCase.description && (
              <p className="text-xs text-neutral-400 mt-1 whitespace-normal break-words">
                {testCase.description}
              </p>
            )}
          </div>
        </div>

        {/* Badges row */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0 rounded font-medium border", typeCfg.className)}>
            {typeCfg.label}
          </Badge>
          <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0 rounded font-medium border", statusCfg.className)}>
            <StatusIcon className={cn("w-3 h-3 mr-1", testCase.status === "running" ? "animate-spin" : "")} strokeWidth={2} />
            {statusCfg.label}
          </Badge>
          {testCase.priority && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 rounded border border-white/[0.08] text-neutral-400">
              {testCase.priority}
            </Badge>
          )}
          <span className="text-[10px] text-neutral-500 ml-auto self-center">
            {formatDate(testCase.createdAt)}
          </span>
        </div>

        {/* Duration */}
        {testCase.duration != null && (
          <p className="text-[10px] text-neutral-500 mt-2">
            Duration: {(testCase.duration / 1000).toFixed(1)}s
          </p>
        )}
      </div>

      {/* Error display */}
      {testCase.errorMessage && (
        <div className="mx-4 mb-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" strokeWidth={1.5} />
            <p className="text-xs text-red-300 font-mono whitespace-pre-wrap break-all">
              {testCase.errorMessage}
            </p>
          </div>
        </div>
      )}

      {/* Collapsible code section */}
      {hasCode && (
        <Collapsible open={codeOpen} onOpenChange={setCodeOpen}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="w-full flex items-center gap-2 px-4 py-2.5 border-t border-white/[0.05] text-xs text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.02] transition-all"
            >
              <Code className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span className="flex-1 text-left">
                {testCase.codeLanguage || "code"}
              </span>
              <ChevronDown
                className={cn(
                  "w-3.5 h-3.5 transition-transform",
                  codeOpen && "rotate-180",
                )}
                strokeWidth={1.5}
              />
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="border-t border-white/[0.05]">
              <div className="flex items-center gap-2 px-4 py-2 bg-white/[0.02]">
                <span className="text-[10px] font-medium text-neutral-500 uppercase tracking-wider">
                  {testCase.codeLanguage || "code"}
                </span>
                <span className="text-[10px] text-neutral-600">|</span>
                <span className="text-[10px] text-neutral-500">
                  {(testCase.code || "").split("\n").length} lines
                </span>
              </div>
              <ScrollArea className="max-h-[300px]">
                <SyntaxHighlighter
                  language={testCase.codeLanguage || "typescript"}
                  style={oneDark}
                  customStyle={{ margin: 0, borderRadius: 0, fontSize: "11px", lineHeight: "1.5", background: "transparent" }}
                  showLineNumbers
                  wrapLines
                  wrapLongLines
                >
                  {testCase.code || ""}
                </SyntaxHighlighter>
              </ScrollArea>
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Actions footer */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-white/[0.05]">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onReRun?.(testCase.id)}
          disabled={isReRunning || testCase.status === "running"}
          className="h-8 px-3 rounded-xl text-xs gap-1.5 text-neutral-400 hover:text-emerald-300 hover:bg-emerald-500/10"
        >
          {isReRunning ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} />
          ) : (
            <Play className="w-3.5 h-3.5" strokeWidth={2} />
          )}
          Re-run
        </Button>
        {onDelete && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onDelete?.(testCase.id)}
            className="h-8 px-3 rounded-xl text-xs gap-1.5 text-neutral-500 hover:text-red-400 hover:bg-red-500/10 ml-auto"
          >
            <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
          </Button>
        )}
      </div>
    </div>
  );
}
