"use client";

import { AlertCircle, Compass, FileEdit, Sparkles } from "lucide-react";

export interface Suggestion {
  id: string;
  title: string;
  desc: string;
  prompt: string;
  icon?: "debug" | "explore" | "plan" | "review";
  wide?: boolean;
  faint?: boolean;
}

const ICONS = {
  debug: AlertCircle,
  explore: Compass,
  plan: Sparkles,
  review: FileEdit,
} as const;

export function EmptyState({
  onSuggestion,
  suggestions,
}: {
  onSuggestion?: (s: Suggestion) => void;
  suggestions?: Suggestion[];
}) {
  const defaults: Suggestion[] = suggestions ?? [
    { id: "debug", title: "Debug a failing test", desc: "Paste an error, I'll find the cause and fix it", prompt: "Help me debug a failing test. I'll paste the error next.", icon: "debug", wide: true },
    { id: "explore", title: "Explore", desc: "Understand a module or flow", prompt: "Explore the codebase and explain the auth flow.", icon: "explore", faint: true },
    { id: "plan", title: "Plan a feature", desc: "Design steps before coding", prompt: "Plan the implementation of a new feature.", icon: "plan", faint: true },
    { id: "review", title: "Review a diff", desc: "Check recent changes for issues", prompt: "Review the current diff for any issues.", icon: "review", wide: true },
  ];

  return (
    <div className="agent-empty">
      <div className="agent-empty-inner">
        <div className="agent-empty-eyebrow">
          <span className="agent-empty-dot" />
          ready
        </div>
        <h1>What do you want to do?</h1>
        <p>Ask me to debug, plan, explore, or review code. I can read files, run commands, search the web, and more.</p>
        <div className="agent-suggest-grid">
          {defaults.map((s) => {
            const Icon = s.icon ? ICONS[s.icon] : Compass;
            return (
              <button
                key={s.id}
                type="button"
                className="agent-suggest"
                data-faint={s.faint ? "true" : "false"}
                onClick={() => onSuggestion?.(s)}
              >
                <div className="agent-suggest-icon">
                  <Icon width={14} height={14} strokeWidth={2} />
                </div>
                <div>
                  <div className="agent-suggest-title">{s.title}</div>
                  <div className="agent-suggest-desc">{s.desc}</div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
