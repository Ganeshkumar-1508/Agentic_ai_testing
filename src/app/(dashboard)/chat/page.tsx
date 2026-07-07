"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, BACKEND_URL } from "@/lib/api/api-client";
import { useProviderStore } from "@/stores/provider-store";
import { TopBar } from "@/components/chat/TopBar";
import { SessionSidebar, type SessionItem, type SessionStatus } from "@/components/chat/SessionSidebar";
import { EmptyState, type Suggestion } from "@/components/chat/EmptyState";
import { Composer, type AttachedFile, type SlashCommand } from "@/components/chat/Composer";
import { MessageBubble, type ChatMessageData, type ToolStatus } from "@/components/chat/MessageBubble";
import { RightRail, type RailTab, type RailTool } from "@/components/chat/RightRail";
import { StatusFooter } from "@/components/chat/StatusFooter";
import { RepoSelector, type RepoInfo } from "@/components/chat/RepoSelector";
import { ModelPickerModal } from "@/components/chat/ModelPickerModal";
import { SessionHealthPanel } from "@/components/session/SessionHealthPanel";
import { ToolsOverviewModal } from "@/components/chat/ToolsOverviewModal";
import { RoleSwitcher } from "@/components/chat/RoleSwitcher";
import { TierBadge } from "@/components/chat/TierBadge";
import "@/components/chat/chat-page.css";

const SID_KEY = "testai_chat_thread";

function loadSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(SID_KEY);
  } catch {
    return null;
  }
}
function saveSessionId(id: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (id) localStorage.setItem(SID_KEY, id);
    else localStorage.removeItem(SID_KEY);
  } catch {}
}

export default function ChatPage() {
  return (
    <Suspense fallback={<AgentPageFallback />}>
      <AgentPageInner />
    </Suspense>
  );
}

function AgentPageFallback() {
  return (
    <div className="chat-shell" data-rail-open="false" data-sidebar-collapsed="false">
      <div style={{ gridColumn: "1 / -1", padding: 24, color: "var(--text-3)" }}>Loading…</div>
    </div>
  );
}

function AgentPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isConfigured, loadProviders } = useProviderStore();

  // Load provider config on mount
  useEffect(() => { loadProviders(); }, [loadProviders]);

  // ── Core state ──────────────────────────────────────────────
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<RepoInfo | null>(null);
  const [selectedBranch, setSelectedBranch] = useState("main");
  const [input, setInput] = useState("");
  const [backendCmds, setBackendCmds] = useState<SlashCommand[]>([]);

  useEffect(() => {
    api.get<{ commands: any[] }>("/api/chat/commands").then((data) => {
      if (data?.commands) {
        setBackendCmds(data.commands.map((c: any) => ({
          cmd: "/" + c.name,
          desc: c.description,
          group: c.flavor === "prompt" ? "Tools" : "Commands",
        })));
      }
    }).catch(() => {});
  }, []);

  const allSlashCmds = useMemo(() => backendCmds, [backendCmds]);
  const [sessionId, setSessionId] = useState<string | null>(
    () => searchParams?.get("thread_id") || loadSessionId()
  );
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingPhase, setStreamingPhase] = useState<"thinking" | "generating" | "">("");
  const [workflowStatus, setWorkflowStatus] = useState<"idle" | "running" | "completed" | "failed">("idle");
  const [sessionHistory, setSessionHistory] = useState<SessionItem[]>([]);
  const [sessionSearch, setSessionSearch] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [railTab, setRailTab] = useState<RailTab>("session");
  const [pageLoading, setPageLoading] = useState(true);

  // ── Token / cost / elapsed (WIRED from SSE) ──────────────────
  const [tokenUsage, setTokenUsage] = useState({ tokens: 0, cost: 0 });
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [model, setModel] = useState<string>("default");
  const [activeTools, setActiveTools] = useState<RailTool[]>([]);
  const [currentTool, setCurrentTool] = useState<string>("");
  const [agentStatus, setAgentStatus] = useState<"idle" | "thinking" | "running_tool" | "generating">("idle");
  const [pendingApprovals, setPendingApprovals] = useState<Map<string, { id: string; command: string; reason?: string }>>(new Map());

  // ── Modal / picker state ────────────────────────────────────
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [toolsOverviewOpen, setToolsOverviewOpen] = useState(false);
  const [currentRole, setCurrentRole] = useState("general");
  const [currentTier, setCurrentTier] = useState(1);

  // ── Composer state ─────────────────────────────────────────
  const [files, setFiles] = useState<AttachedFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [slashSelectedIdx, setSlashSelectedIdx] = useState(0);

  // ── Refs ────────────────────────────────────────────────────
  const streamEventRef = useRef<EventSource | null>(null);
  const startTimeRef = useRef<number>(0);
  const endRef = useRef<HTMLDivElement>(null);
  const assistantMsgRef = useRef<ChatMessageData | null>(null);

  // ── Slash detection ────────────────────────────────────────
  const slashOpen = useMemo(() => {
    const t = input.trimStart();
    if (!t.startsWith("/")) return false;
    if (t.includes(" ")) return false;
    return true;
  }, [input]);

  const filteredCommands = useMemo(() => {
    if (!slashOpen) return [];
    const t = input.trimStart().toLowerCase();
    return allSlashCmds.filter((c) => c.cmd.toLowerCase().startsWith(t)).slice(0, 6);
  }, [slashOpen, input]);

  // ── Load session on mount / when sessionId changes ──────────
  useEffect(() => {
    if (!sessionId) {
      setPageLoading(false);
      return;
    }
    saveSessionId(sessionId);
    api
      .get<any>(`/api/chat/threads/${sessionId}/messages?limit=500`)
      .then((data) => {
        if (!data?.messages) return;
        const msgs: ChatMessageData[] = [];
        for (const m of data.messages) {
          if (m.role === "user") {
            msgs.push({ id: `msg-${msgs.length}`, role: "user", content: m.content || "", timestamp: Date.now() });
          } else if (m.role === "assistant") {
            msgs.push({
              id: `msg-${msgs.length}`,
              role: "assistant",
              content: m.content || "",
              reasoning: m.reasoning_content ? m.reasoning_content.split("\n").filter(Boolean) : undefined,
              timestamp: Date.now(),
            });
          } else if (m.role === "tool") {
            msgs.push({ id: `msg-${msgs.length}`, role: "tool", content: (m.content || "").slice(0, 500), timestamp: Date.now() });
          }
        }
        setMessages(msgs);
      })
      .catch(() => {})
      .finally(() => setPageLoading(false));

    api
      .get<{ threads?: any[] }>("/api/chat/threads?limit=30")
      .then((d) => {
        const items: SessionItem[] = (d?.threads || []).map((t: any, i: number) => ({
          id: t.id || `t-${i}`,
          title: t.title || "Untitled",
          status: (t.status as SessionStatus) || "completed",
          meta: t.last_message_at ? new Date(t.last_message_at).toLocaleString() : undefined,
        }));
        setSessionHistory(items);
      })
      .catch(() => {});

    api
      .get<{ tools?: any[]; toolsets?: Record<string, { label: string; description: string }> }>("/api/ops/tools")
      .then((d) => {
        const tools = (d?.tools || []).slice(0, 3).map((t: any) => ({
          name: t.name || t.tool_name || "tool",
          status: "done" as const,
          durationMs: t.duration_ms || 0,
        }));
        setActiveTools(tools);
      })
      .catch(() => {});

    api
      .get<Array<{ provider?: string; model?: string }>>("/api/settings/providers")
      .then((d) => {
        const first = d?.[0];
        if (first?.model) setModel(first.model);
      })
      .catch(() => {});
  }, [sessionId]);

  // ── Auto-scroll ─────────────────────────────────────────────
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Elapsed timer while running ─────────────────────────────
  useEffect(() => {
    if (!isStreaming) return;
    const id = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [isStreaming]);

  // ── Escape to stop ─────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isStreaming) handleStop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming]);

  // ── Stream cleanup ─────────────────────────────────────────
  const cleanupStream = useCallback(() => {
    if (streamEventRef.current) {
      streamEventRef.current.close();
      streamEventRef.current = null;
    }
    setIsStreaming(false);
    setStreamingPhase("");
    assistantMsgRef.current = null;
  }, []);

  const handleStop = useCallback(() => {
    if (sessionId) {
      api.post(`/api/delegate/${sessionId}/cancel`).catch(() => {});
    }
    cleanupStream();
  }, [sessionId, cleanupStream]);

  // ── SSE connection ─────────────────────────────────────────
  const connectSSE = useCallback(
    (sid: string) => {
      cleanupStream();
      const url = `${BACKEND_URL}/api/chat/threads/${encodeURIComponent(sid)}/messages`;
      const es = new EventSource(url);
      streamEventRef.current = es;
      startTimeRef.current = Date.now();
      setElapsedSeconds(0);
      setTokenUsage({ tokens: 0, cost: 0 });

      es.addEventListener("connected", () => {
        setWorkflowStatus("running");
      });

      es.addEventListener("chat.run.started", () => {
        setWorkflowStatus("running");
        setStreamingPhase("generating");
      });

      es.addEventListener("chat.message.start", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data?.message_id && !assistantMsgRef.current) {
            assistantMsgRef.current = {
              id: data.message_id,
              role: "assistant",
              content: "",
              timestamp: Date.now(),
            };
          }
        } catch {}
      });

      es.addEventListener("chat.token", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const delta = data?.delta || "";
          if (!delta) return;
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === assistantMsgRef.current?.id);
            if (idx >= 0) {
              const next = prev.slice();
              next[idx] = { ...next[idx], content: next[idx].content + delta };
              return next;
            }
            if (assistantMsgRef.current) {
              return [...prev, { ...assistantMsgRef.current, content: delta }];
            }
            const newMsg: ChatMessageData = {
              id: `a-${Date.now()}`,
              role: "assistant",
              content: delta,
              timestamp: Date.now(),
            };
            assistantMsgRef.current = newMsg;
            return [...prev, newMsg];
          });
        } catch {}
      });

      es.addEventListener("chat.tool.started", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const toolName = data?.tool_name || "tool";
          setCurrentTool(toolName);
          setAgentStatus("running_tool");
          setActiveTools((prev) => {
            const filtered = prev.filter((t) => t.name !== toolName);
            return [...filtered, { name: toolName, status: "running" }];
          });
        } catch {}
      });

      es.addEventListener("chat.tool.completed", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const toolName = data?.tool_name || "tool";
          setCurrentTool("");
          setAgentStatus("generating");
          setActiveTools((prev) => {
            const filtered = prev.filter((t) => t.name !== toolName);
            return [...filtered, { name: toolName, status: data?.is_error ? "error" : "done", durationMs: 0 }];
          });
        } catch {}
      });

      es.addEventListener("chat.message.end", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (typeof data?.prompt_tokens === "number" && typeof data?.completion_tokens === "number") {
            const total = (data.prompt_tokens || 0) + (data.completion_tokens || 0);
            setTokenUsage((prev) => ({ tokens: total, cost: prev.cost + (data?.cost_usd || 0) }));
          }
        } catch {}
      });

      es.addEventListener("chat.error", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          toast.error(`Chat error: ${data?.message || "unknown"}`);
        } catch {}
        setWorkflowStatus("failed");
        cleanupStream();
      });

      es.addEventListener("chat.run.cancelled", () => {
        setWorkflowStatus("failed");
        cleanupStream();
      });

      es.addEventListener("chat.run.completed", () => {
        setWorkflowStatus("completed");
        setCurrentTool("");
        setAgentStatus("idle");
        cleanupStream();
      });

      es.addEventListener("error", () => {
        if (streamEventRef.current) {
          setWorkflowStatus("failed");
          cleanupStream();
        }
      });
    },
    [cleanupStream]
  );

  // ── Submit (POST /api/jobs) ─────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (input.trim().length === 0 || isStreaming) return;
    if (!isConfigured()) {
      toast.error("No LLM provider configured. Go to Settings → LLM Providers to add one.");
      return;
    }
    const text = input;
    const userMsg: ChatMessageData = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);
    setWorkflowStatus("running");
    setStreamingPhase("thinking");
    setTokenUsage({ tokens: 0, cost: 0 });
    setElapsedSeconds(0);
    setCurrentTool("");
    setAgentStatus("thinking");
    setActiveTools([]);
    startTimeRef.current = Date.now();

    try {
      const { toJobSpecFromChatComposer } = await import("@/lib/adapters/job-spec");
      const payload: Record<string, unknown> = {
        prompt: text,
        mode: "auto",
        tier: currentTier,
        repo_url: selectedRepo?.full_name ? `https://github.com/${selectedRepo.full_name}` : "",
        branch: selectedBranch,
      };
      if (sessionId) payload.session_id = sessionId;
      const spec = toJobSpecFromChatComposer(payload);
      if (sessionId) spec.context = { ...(spec.context || {}), session_id: sessionId };

      const result = await api.post<{ run_id?: string; thread_id?: string; session_id?: string; error?: string }>("/api/jobs", spec);
      const threadId = result.thread_id || result.run_id || result.session_id || "";
      if (!threadId) throw new Error(result.error || "Failed to start agent run");
      setSessionId(threadId);
      setStreamingPhase("generating");
      connectSSE(threadId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Connection failed";
      toast.error(msg);
      setIsStreaming(false);
      setWorkflowStatus("failed");
      setStreamingPhase("");
    }
  }, [input, isStreaming, sessionId, connectSSE]);

  // ── Approve / deny (POST /api/approve) ──────────────────────
  const handleApprove = useCallback(
    async (approvalId: string, scope?: "once" | "session" | "always") => {
      try {
        await api.post("/api/approve", { approval_id: approvalId, approved: true, scope: scope || "once" });
        setPendingApprovals((prev) => {
          const next = new Map(prev);
          next.delete(approvalId);
          return next;
        });
      } catch {
        toast.error("Failed to approve");
      }
    },
    []
  );
  const handleDeny = useCallback(
    async (approvalId: string) => {
      try {
        await api.post("/api/approve", { approval_id: approvalId, approved: false });
        setPendingApprovals((prev) => {
          const next = new Map(prev);
          next.delete(approvalId);
          return next;
        });
      } catch {
        toast.error("Failed to deny");
      }
    },
    []
  );

  // ── Reactions (POST /api/sessions/{id}/reaction) ────────────
  const handleReact = useCallback(
    async (msgId: string, kind: "up" | "down" | "none") => {
      try {
        if (sessionId) {
          await api.post(`/api/sessions/${sessionId}/reaction`, { message_id: msgId, reaction_type: kind });
        }
      } catch {}
    },
    [sessionId]
  );

  // ── Session control ─────────────────────────────────────────
  const handleNewChat = useCallback(() => {
    cleanupStream();
    setMessages([]);
    setWorkflowStatus("idle");
    setSessionId(null);
    saveSessionId(null);
    setTokenUsage({ tokens: 0, cost: 0 });
    setCurrentTool("");
    setAgentStatus("idle");
    setActiveTools([]);
    setElapsedSeconds(0);
    setActiveTools([]);
    setPendingApprovals(new Map());
    setFiles([]);
    try { sessionStorage.removeItem("agent_prompt"); } catch {}
  }, [cleanupStream]);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === sessionId) return;
      cleanupStream();
      router.push(`/chat?thread_id=${encodeURIComponent(id)}`);
    },
    [sessionId, cleanupStream, router]
  );

  // ── Slash handler ───────────────────────────────────────────
  const handleSlashSelect = useCallback(
    async (cmd: SlashCommand) => {
      const isBackend = backendCmds.some((b) => b.cmd === cmd.cmd);
      if (isBackend) {
        // Dispatch to backend slash API — bypasses the LLM
        const name = cmd.cmd.replace("/", "");
        try {
          const res = await api.post<{ output: string }>("/api/chat/slash", {
            command: name, args: "", session_id: sessionId,
          });
          if (res?.output) {
            setMessages((prev) => [...prev, {
              id: `slash-${Date.now()}`, role: "assistant",
              content: res.output, timestamp: Date.now(),
            }]);
          }
        } catch {
          // Fallback: just insert into input
          setInput(cmd.cmd + " ");
        }
      } else {
        setInput(cmd.cmd + " ");
      }
    },
    [backendCmds, sessionId]
  );

  // ── Drag & drop ─────────────────────────────────────────────
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer?.types?.includes("Files")) setDragOver(true);
  }, []);
  const handleDragLeave = useCallback(() => setDragOver(false), []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files || []);
    if (dropped.length > 0) {
      setFiles((prev) => [
        ...prev,
        ...dropped.map((f) => ({ name: f.name, size: f.size, mime: f.type })),
      ]);
    }
  }, []);

  // ── Render ──────────────────────────────────────────────────
  return (
    <div className="chat-shell" data-rail-open={railOpen ? "true" : "false"} data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}>
      <TopBar
        onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
        onToggleRail={() => setRailOpen((v) => !v)}
        onOpenSearch={() => toast.info("Use ⌘K to open the command palette (top right).")}
        onOpenSettings={() => router.push("/settings")}
        railOpen={railOpen}
        sidebarCollapsed={sidebarCollapsed}
      />

      {!sidebarCollapsed && (
        <SessionSidebar
          sessions={sessionHistory.filter((s) => !sessionSearch || s.title.toLowerCase().includes(sessionSearch.toLowerCase()))}
          activeId={sessionId}
          onSelect={handleSelectSession}
          onNewChat={handleNewChat}
          onSearch={setSessionSearch}
          searchValue={sessionSearch}
        />
      )}

      <main className="chat-main">
        {!isConfigured() && (
          <div className="mx-4 mt-4 px-4 py-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-300 text-xs flex items-center gap-3">
            <span className="font-medium">No LLM provider configured.</span>
            <button onClick={() => router.push("/settings")} className="underline hover:text-amber-200 transition-colors">
              Go to Settings → LLM Providers to add one.
            </button>
          </div>
        )}
        {messages.length === 0 ? (
          <EmptyState
            onSuggestion={(s) => {
              setInput(s.prompt);
            }}
          />
        ) : (
          <div className="chat-feed">
            {messages.map((m, i) => {
              // attach pending approval to the last assistant message
              const enriched = m.role === "assistant" && i === messages.length - 1 && pendingApprovals.size > 0
                ? {
                    ...m,
                    approval: Array.from(pendingApprovals.values())[0],
                  }
                : m;
              return (
                <MessageBubble
                  key={m.id}
                  message={enriched}
                  index={i}
                  onApprove={handleApprove}
                  onDeny={handleDeny}
                  onReact={handleReact}
                  busy={isStreaming}
                />
              );
            })}
            <div ref={endRef} />
          </div>
        )}

        {isStreaming && (
          <StatusFooter
            info={{
              model,
              tokensUsed: tokenUsage.tokens,
              costUsd: tokenUsage.cost,
              elapsedSeconds,
              currentTool,
              agentStatus,
            }}
          />
        )}

        {sessionId && !isStreaming && (
          <div className="px-4 py-3 border-t border-zinc-800/20">
            <SessionHealthPanel sessionId={sessionId} />
          </div>
        )}

        <RepoSelector
          selectedRepo={selectedRepo}
          onSelect={setSelectedRepo}
          selectedBranch={selectedBranch}
          onBranchChange={setSelectedBranch}
        />

        <div className="flex items-center justify-between px-4 pt-2 pb-1">
          <RoleSwitcher
            currentRole={currentRole}
            onRoleChange={setCurrentRole}
            disabled={isStreaming}
          />
          <TierBadge
            tier={currentTier}
            onChange={setCurrentTier}
            disabled={isStreaming}
          />
        </div>

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          onStop={handleStop}
          streaming={isStreaming}
          files={files}
          onRemoveFile={(idx) => setFiles((prev) => prev.filter((_, i) => i !== idx))}
          onAttach={() => {
            const input = document.createElement("input");
            input.type = "file";
            input.multiple = true;
            input.accept = ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.gif,.svg,.txt,.csv,.json,.md,.py,.js,.ts,.tsx,.jsx,.css,.html,.yaml,.yml,.toml";
            input.onchange = () => {
              const newFiles = Array.from(input.files || []).map((f) => ({
                name: f.name, size: f.size, mime: f.type,
              }));
              setFiles((prev) => [...prev, ...newFiles]);
            };
            input.click();
          }}
          onVoice={() => toast.info("Voice input not wired yet")}
          onModel={() => setModelPickerOpen(true)}
          onTools={() => setToolsOverviewOpen(true)}
          modelLabel={model}
          toolsCount={activeTools.length}
          slashOpen={slashOpen}
          slashCommands={filteredCommands}
          slashSelectedIdx={slashSelectedIdx}
          onSlashSelect={handleSlashSelect}
          onSlashClose={() => setInput("")}
          dragOver={dragOver}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        />
      </main>

      <ModelPickerModal
        open={modelPickerOpen}
        onClose={() => setModelPickerOpen(false)}
        currentModel={model}
        onSelect={() => {}} // UI reference only — model is set via provider config
      />
      <ToolsOverviewModal
        open={toolsOverviewOpen}
        onClose={() => setToolsOverviewOpen(false)}
        activeTools={activeTools}
      />

      {railOpen && (
        <RightRail
          activeTab={railTab}
          onTabChange={setRailTab}
          onClose={() => setRailOpen(false)}
          sessionEyebrow={sessionId ? `session #${sessionId.slice(0, 8)}` : undefined}
          sessionTitle={messages.find((m) => m.role === "user")?.content?.slice(0, 60) || "New session"}
          sessionStatus={workflowStatus}
          sessionStartedAt={sessionId ? new Date().toLocaleTimeString() : undefined}
          tokenUsed={tokenUsage.tokens}
          tokenBudget={200000}
          model={model}
          cost={tokenUsage.cost}
          costBudget={5}
          links={
            sessionId
              ? [
                  { label: "branch", value: "fix/jobs-spec", tall: true },
                  { label: "session", value: sessionId.slice(0, 12) },
                ]
              : undefined
          }
          tools={activeTools}
          onEndSession={handleNewChat}
        />
      )}
    </div>
  );
}
