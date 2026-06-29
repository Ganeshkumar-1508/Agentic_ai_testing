"use client";

import { useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import { Sparkles, ArrowRight, Bug, TestTube, BarChart3, FileText } from "lucide-react";

type SuggestionItem = {
  label: string;
  icon: typeof Sparkles;
  description?: string;
};

type Message = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name?: string;
};

const FALLBACK_SUGGESTIONS: SuggestionItem[] = [
  { label: "Run a test suite", icon: TestTube },
  { label: "Compare two pipeline runs", icon: BarChart3 },
  { label: "Show available tools", icon: Sparkles },
  { label: "Generate a pipeline report", icon: FileText },
];

function generateSuggestions(messages: Message[], input: string): SuggestionItem[] {
  if (input.trim()) return [];

  const assistantMsgs = messages.filter((m) => m.role === "assistant" && m.content);
  const lastAssistant = assistantMsgs[assistantMsgs.length - 1];

  if (!lastAssistant) return FALLBACK_SUGGESTIONS;

  const lastContent = lastAssistant.content.toLowerCase();
  const items: SuggestionItem[] = [];

  if (lastContent.includes("test") || lastContent.includes("pytest") || lastContent.includes("result")) {
    items.push({ label: "Fix the failing tests", icon: Bug });
    items.push({ label: "Show me the test code", icon: FileText });
  }

  if (lastContent.includes("error") || lastContent.includes("failed") || lastContent.includes("traceback")) {
    items.push({ label: "Explain what caused this error", icon: Sparkles });
    items.push({ label: "Fix this issue automatically", icon: Bug });
  }

  if (lastContent.includes("pipeline") || lastContent.includes("run") || lastContent.includes("duration")) {
    items.push({ label: "Re-run with different parameters", icon: BarChart3 });
    items.push({ label: "Export as a report", icon: FileText });
    items.push({ label: "Compare with a previous run", icon: BarChart3 });
  }

  if (lastAssistant.tool_name || lastContent.includes("tool")) {
    items.push({ label: "What tools are available?", icon: Sparkles });
    items.push({ label: "Run a custom tool", icon: ArrowRight });
  }

  if (items.length === 0) {
    items.push({ label: "Explain this in more detail", icon: Sparkles });
    items.push({ label: "Show me the code changes", icon: FileText });
    items.push({ label: "Run this analysis again", icon: ArrowRight });
  }

  return items.slice(0, 4);
}

interface ChatSuggestionsProps {
  messages: Message[];
  input: string;
  onSuggestion: (text: string) => void;
}

export function ChatSuggestions({ messages, input, onSuggestion }: ChatSuggestionsProps) {
  const suggestions = useMemo(() => generateSuggestions(messages, input), [messages, input]);

  if (suggestions.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 px-1" data-slot="suggestions-list">
      {suggestions.map((s, index) => (
        <motion.button
          key={s.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 + index * 0.06, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          onClick={() => onSuggestion(s.label)}
          className="group inline-flex items-center gap-1.5 rounded-full border border-zinc-800/50 bg-zinc-900/60 px-3.5 py-1.5 text-[11px] font-medium text-zinc-400 transition-all hover:border-emerald-500/30 hover:bg-emerald-500/10 hover:text-emerald-300 active:scale-[0.97]"
        >
          <s.icon size={12} strokeWidth={1.5} className="text-zinc-500 group-hover:text-emerald-400 transition-colors" />
          {s.label}
        </motion.button>
      ))}
    </div>
  );
}
