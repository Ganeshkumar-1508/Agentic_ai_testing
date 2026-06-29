"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, MessageSquare, X, CornerDownRight, type LucideIcon } from "lucide-react";
import type { KGNode, KnowledgeGraph } from "./types";
import { getNodeTone, NODE_TYPE_LABEL } from "./constants";
import { nodeDisplayName, nodeSecondaryLabel } from "./view-model";
import { cn } from "@/lib/utils";

interface AskPanelProps {
  graph: KnowledgeGraph | null;
  onFocusNode: (nodeId: string) => void;
}

interface AskMessage {
  id: string;
  type: "question" | "answer";
  text: string;
  hits?: Array<{ node: KGNode; score: number }>;
  timestamp: number;
}

export function AskPanel({ graph, onFocusNode }: AskPanelProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<AskMessage[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  const nodeIndex = useMemo(() => {
    if (!graph) return null;
    const index = new Map<string, KGNode[]>();
    for (const node of graph.nodes) {
      for (const word of [...node.name.split(/[_/.\- ]/), ...node.tags, node.language ?? ""]) {
        const key = word.toLowerCase();
        if (!key || key.length < 2) continue;
        const existing = index.get(key) ?? [];
        existing.push(node);
        index.set(key, existing);
      }
      const fileKey = (node.file ?? node.filePath ?? "").toLowerCase();
      if (fileKey) {
        index.set(fileKey, [...(index.get(fileKey) ?? []), node]);
      }
    }
    return index;
  }, [graph]);

  function searchNodes(query: string): Array<{ node: KGNode; score: number }> {
    if (!nodeIndex || !query.trim()) return [];
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    const scores = new Map<string, { node: KGNode; score: number }>();

    for (const node of graph?.nodes ?? []) {
      let score = 0;
      const name = node.name.toLowerCase();
      const file = (node.file ?? node.filePath ?? "").toLowerCase();
      const summary = (node.summary ?? "").toLowerCase();
      const tags = node.tags.map((t) => t.toLowerCase());

      for (const term of terms) {
        if (name === term) score += 10;
        else if (name.startsWith(term)) score += 5;
        else if (name.includes(term)) score += 3;
        if (file.includes(term)) score += 2;
        if (tags.some((t) => t.includes(term))) score += 2;
        if (summary.includes(term)) score += 1;
      }

      if (score > 0) {
        scores.set(node.id, { node, score });
      }
    }

    return Array.from(scores.values())
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
  }

  function handleAsk() {
    const q = input.trim();
    if (!q) return;

    const question: AskMessage = {
      id: `ask-${Date.now()}`,
      type: "question",
      text: q,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, question]);
    setInput("");
    setIsSearching(true);

    setTimeout(() => {
      const hits = searchNodes(q);
      const answer: AskMessage = {
        id: `ans-${Date.now()}`,
        type: "answer",
        text:
          hits.length > 0
            ? `Found ${hits.length} matching symbol${hits.length === 1 ? "" : "s"} in the knowledge graph.`
            : "No nodes matched your query in the current graph. Try different terms or check the graph has been indexed.",
        hits: hits.length > 0 ? hits : undefined,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, answer]);
      setIsSearching(false);
    }, 200);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto pb-3">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <MessageSquare className="mb-3 h-8 w-8 text-neutral-700" strokeWidth={1.2} />
            <p className="text-[12px] font-medium text-neutral-400">Ask about this codebase</p>
            <p className="mt-1 max-w-[260px] text-[10px] leading-5 text-neutral-600">
              Search for symbols, files, classes, or relationships in the current knowledge graph.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-1.5">
              {(graph?.nodes?.length ? graph.nodes.slice(0, 5).map(n => nodeDisplayName(n)) : ["auth", "UserService", "database", "routes", "pipeline"]).map((hint) => (
                <button
                  key={hint}
                  type="button"
                  onClick={() => {
                    setInput(hint);
                  }}
                  className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-1 text-[9px] font-mono text-neutral-500 transition-colors hover:border-white/[0.1] hover:text-neutral-200"
                >
                  {hint}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
              >
                {msg.type === "question" ? (
                  <div className="flex items-start gap-2 rounded-2xl border border-white/[0.06] bg-emerald-500/8 px-3 py-2.5">
                    <CornerDownRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" strokeWidth={1.8} />
                    <div>
                      <p className="text-[11px] font-medium text-neutral-100">{msg.text}</p>
                      <p className="mt-0.5 text-[8px] font-mono text-neutral-600">
                        {new Date(msg.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2 rounded-2xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
                    <p className="text-[11px] leading-6 text-neutral-300">{msg.text}</p>
                    {msg.hits && msg.hits.length > 0 ? (
                      <div className="space-y-1">
                        {msg.hits.map(({ node, score }) => {
                          const tone = getNodeTone(node.type);
                          return (
                            <button
                              key={node.id}
                              type="button"
                              onClick={() => onFocusNode(node.id)}
                              className="flex w-full items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.03] px-2.5 py-2 text-left transition-colors hover:border-white/[0.09] hover:bg-white/[0.05]"
                            >
                              <span className={cn("h-2 w-2 shrink-0 rounded-full", tone.dot)} />
                              <div className="min-w-0 flex-1">
                                <div className="truncate text-[10px] font-medium text-neutral-100">
                                  {nodeDisplayName(node)}
                                </div>
                                <div className="truncate text-[9px] font-mono text-neutral-500">
                                  {nodeSecondaryLabel(node)}
                                </div>
                              </div>
                              <span className="rounded-md border border-white/[0.06] px-1.5 py-0.5 text-[7px] font-mono uppercase tracking-[0.18em] text-neutral-500">
                                {NODE_TYPE_LABEL[node.type] ?? node.type}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
        {isSearching ? (
          <div className="flex items-center gap-2 px-1 py-1">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            <span className="text-[10px] font-mono text-neutral-500">Searching graph…</span>
          </div>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-2 border-t border-white/[0.06] bg-white/[0.02] px-2 py-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-600" strokeWidth={1.8} />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this codebase…"
            className="h-8 w-full rounded-xl border border-white/[0.08] bg-white/[0.03] pl-8 pr-3 text-[10px] font-mono text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-400/30 focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={handleAsk}
          disabled={!input.trim() || isSearching}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-500/12 text-emerald-300 transition-colors hover:bg-emerald-500/20 disabled:opacity-30"
        >
          <CornerDownRight className="h-3.5 w-3.5" strokeWidth={1.8} />
        </button>
      </div>
    </div>
  );
}
