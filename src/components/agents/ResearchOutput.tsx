"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ResearchOutputData } from "@/lib/types/workflow";
import {
  FileSearch,
  Database,
  Bot,
  AlertTriangle,
  CheckCircle,
  Target,
  Code2,
  Globe,
} from "lucide-react";

interface ResearchOutputProps {
  output: ResearchOutputData | null;
  className?: string;
}

export function ResearchOutput({ output, className }: ResearchOutputProps) {
  if (!output) {
    return (
      <div className={cn("bg-surface border border-white/[0.05] rounded-[1.5rem] p-6 text-center", className)}>
        <FileSearch className="w-8 h-8 text-neutral-600 mx-auto mb-3" strokeWidth={1.2} />
        <p className="text-sm text-neutral-500">Research phase not started yet</p>
      </div>
    );
  }

  const { projectSummary, techStack, aiPatterns, environment, recommendedFocus } = output;
  const detectedAIPatterns = aiPatterns?.filter((p) => p.detected) || [];

  return (
    <div className={cn("bg-surface border border-white/[0.05] rounded-[1.5rem] overflow-hidden", className)}>
      {/* Header */}
      <div className="p-5 border-b border-white/[0.05]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <FileSearch className="w-5 h-5 text-emerald-400" strokeWidth={1.5} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-neutral-100">
              Research Analysis
            </h3>
            <p className="text-xs text-neutral-500">Phase 0 — Repository Analysis Complete</p>
          </div>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Tech Stack */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Code2 className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />
            <span className="text-sm font-semibold text-neutral-200">Tech Stack</span>
          </div>
          {techStack && Object.keys(techStack).length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {Object.entries(techStack).map(([key, value]) => {
                if (!value || key === 'configFiles' || key === 'confidence') return null;
                return (
                  <Badge
                    key={key}
                    variant="outline"
                    className="bg-white/[0.03] border-white/[0.08] text-neutral-300 text-xs"
                  >
                    {key.replace(/([A-Z])/g, ' $1').trim()}: {String(value)}
                  </Badge>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-neutral-500">No tech stack data</p>
          )}
        </div>

        <Separator className="bg-white/[0.06]" />

        {/* AI Patterns */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Bot className={cn(
              "w-4 h-4",
              detectedAIPatterns.length > 0 ? "text-zinc-400" : "text-neutral-500",
            )} strokeWidth={1.5} />
            <span className="text-sm font-semibold text-neutral-200">
              AI Patterns {detectedAIPatterns.length > 0 && `(${detectedAIPatterns.length} detected)`}
            </span>
          </div>

          {detectedAIPatterns.length > 0 ? (
            <div className="space-y-2">
              {detectedAIPatterns.map((pattern, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 p-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl"
                >
                  <CheckCircle className="w-4 h-4 text-zinc-400 shrink-0 mt-0.5" strokeWidth={2} />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-neutral-200">{pattern.name}</span>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px] px-1.5 py-0",
                          pattern.confidence === 'high' ? 'text-emerald-400 border-emerald-500/30' :
                          pattern.confidence === 'medium' ? 'text-amber-400 border-amber-500/30' :
                          'text-neutral-400 border-neutral-500/30',
                        )}
                      >
                        {pattern.confidence}
                      </Badge>
                    </div>
                    <p className="text-xs text-neutral-500 mt-0.5">
                      Frameworks: {pattern.frameworks?.join(', ') || 'N/A'}
                    </p>
                    {pattern.files && pattern.files.length > 0 && (
                      <p className="text-[10px] text-neutral-600 mt-1">
                        Files: {pattern.files.slice(0, 3).join(', ')}
                        {pattern.files.length > 3 && ` +${pattern.files.length - 3} more`}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-2 p-3 bg-neutral-500/5 border border-neutral-500/10 rounded-xl">
              <AlertTriangle className="w-4 h-4 text-neutral-500 shrink-0" strokeWidth={1.5} />
              <p className="text-xs text-neutral-500">No AI/agent patterns detected</p>
            </div>
          )}
        </div>

        <Separator className="bg-white/[0.06]" />

        {/* Environment */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
            <span className="text-sm font-semibold text-neutral-200">Environment Blueprint</span>
          </div>
          {environment && Object.keys(environment).length > 0 ? (
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(environment).map(([key, value]) => {
                if (!value) return null;
                return (
                  <div
                    key={key}
                    className="bg-white/[0.02] border border-white/[0.06] rounded-lg px-3 py-2"
                  >
                    <p className="text-[10px] text-neutral-500 uppercase tracking-wider mb-0.5">
                      {key.replace(/([A-Z])/g, ' $1').trim()}
                    </p>
                    <p className="text-xs text-neutral-300 font-mono truncate">
                      {Array.isArray(value) ? value.join(', ') : String(value)}
                    </p>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-neutral-500">No environment data</p>
          )}
        </div>

        <Separator className="bg-white/[0.06]" />

        {/* Recommended Focus */}
        {recommendedFocus && recommendedFocus.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Target className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
              <span className="text-sm font-semibold text-neutral-200">Recommended Test Focus</span>
            </div>
            <ul className="space-y-1.5">
              {recommendedFocus.map((item, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-neutral-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/60 mt-1.5 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

