"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MagnifyingGlassIcon, Cross2Icon } from "@radix-ui/react-icons";

const ROUTES = [
  { label: "Dashboard", href: "/dashboard", keywords: "home overview main" },
  { label: "Pull Requests", href: "/pull-requests", keywords: "pr prs github gitlab" },
  { label: "Pipeline", href: "/pipeline", keywords: "pipeline run test ci" },
  { label: "Chat", href: "/chat", keywords: "agent chat ask assistant" },
  { label: "Requirements", href: "/requirements", keywords: "requirement spec feature" },
  { label: "Test Cases", href: "/test-cases", keywords: "test cases manual" },
  { label: "Traceability", href: "/traceability", keywords: "trace coverage matrix" },
  { label: "Scheduler", href: "/cron", keywords: "cron schedule job periodic" },
  { label: "Sessions", href: "/sessions", keywords: "session history log" },
  { label: "Analytics", href: "/analytics", keywords: "analytics stats metrics" },
  { label: "Settings", href: "/settings", keywords: "settings config preferences" },
  { label: "Tools", href: "/tools", keywords: "tools registry mcp" },
  { label: "Skills", href: "/skills", keywords: "skills capabilities" },
  { label: "Sandbox", href: "/sandbox", keywords: "sandbox container docker" },
  { label: "Flaky Tests", href: "/flaky-tests", keywords: "flaky unstable quarantine" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
      }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => {
      setOpen(true);
      setQuery("");
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("opencmdk", onOpen as EventListener);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("opencmdk", onOpen as EventListener);
    };
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  const filtered = query.trim()
    ? ROUTES.filter((r) =>
        r.label.toLowerCase().includes(query.toLowerCase()) ||
        r.keywords.toLowerCase().includes(query.toLowerCase()))
    : ROUTES;

  const navigate = useCallback((href: string) => {
    setOpen(false);
    window.location.href = href;
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIdx((i) => Math.max(i - 1, 0)); }
    if (e.key === "Enter" && filtered[selectedIdx]) { navigate(filtered[selectedIdx].href); }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-zinc-950/60 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 200, damping: 25 }}
            className="w-full max-w-lg bg-zinc-900/95 border border-zinc-700/50 rounded-2xl shadow-2xl overflow-hidden backdrop-blur-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800/60">
              <MagnifyingGlassIcon className="w-4 h-4 text-zinc-500 shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => { setQuery(e.target.value); setSelectedIdx(0); }}
                onKeyDown={handleKeyDown}
                placeholder="Search pages..."
                className="flex-1 bg-transparent border-none text-sm text-zinc-200 placeholder-zinc-600 outline-none"
              />
              <div className="flex items-center gap-1.5 text-[9px] text-zinc-700 font-mono">
                <kbd className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700">Esc</kbd>
                <span className="text-zinc-800">to close</span>
              </div>
            </div>

            <div className="max-h-[300px] overflow-y-auto p-2 space-y-0.5">
              {filtered.length === 0 ? (
                <div className="text-center py-6 text-xs text-zinc-700">No results found</div>
              ) : (
                filtered.map((route, idx) => (
                  <button
                    key={route.href}
                    onClick={() => navigate(route.href)}
                    onMouseEnter={() => setSelectedIdx(idx)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs transition-all ${
                      idx === selectedIdx
                        ? "bg-emerald-500/10 text-emerald-300 border-l-2 border-emerald-400"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30 border-l-2 border-transparent"
                    }`}
                  >
                    <span className="flex-1 text-left font-medium">{route.label}</span>
                    <span className="text-[9px] text-zinc-700 font-mono">{route.href}</span>
                  </button>
                ))
              )}
            </div>

            <div className="flex items-center gap-3 px-4 py-2 border-t border-zinc-800/60 text-[9px] text-zinc-700">
              <span className="flex items-center gap-1"><kbd className="px-1 rounded bg-zinc-800 border border-zinc-700">↑↓</kbd> navigate</span>
              <span className="flex items-center gap-1"><kbd className="px-1 rounded bg-zinc-800 border border-zinc-700">Enter</kbd> open</span>
              <span className="flex items-center gap-1 ml-auto"><kbd className="px-1 rounded bg-zinc-800 border border-zinc-700">Cmd+K</kbd> toggle</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
