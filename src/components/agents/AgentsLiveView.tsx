"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Bot, Cpu, Loader2, Workflow } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api/api-client";

type Agent = {
  id: string;
  name: string;
  role: string;
  depth: number;
  status: string;
  goal: string;
  currentTask: string;
  toolCurrentlyInvoked: string;
  skillCurrentlyInvoked: string | null;
  sandboxRuntime: string;
  runtimeContainerId: string;
  lastActivityTimestamp: string | null;
  interrupted: boolean;
};

type ActiveSession = {
  id: string;
  status: string;
  totalTokens: number;
  totalCost: number;
  createdAt: string | null;
} | null;

type Payload = {
  unreachable: boolean;
  agents: Agent[];
  activeSession: ActiveSession;
  toolCallsTotal: number;
  fetchedAt: string;
  error?: string;
};

const POLL_MS = 4000;

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "running" || status === "ok") return "default";
  if (status === "completed" || status === "idle") return "secondary";
  if (status === "error" || status === "cancelled" || status === "interrupted") return "destructive";
  return "outline";
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const delta = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.round(delta / 60)}m ago`;
  return `${Math.round(delta / 3600)}h ago`;
}

export function AgentsLiveView() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      try {
        const json = await api.get<Payload>("/api/agents/active", { _: Date.now().toString() });
        if (!cancelled) {
          setData(json);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setData({
            unreachable: true,
            agents: [],
            activeSession: null,
            toolCallsTotal: 0,
            fetchedAt: new Date().toISOString(),
            error: "fetch_failed",
          });
          setLoading(false);
        }
      } finally {
        if (!cancelled) timer = setTimeout(tick, POLL_MS);
      }
    }

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const agents = data?.agents ?? [];
  const session = data?.activeSession ?? null;
  const unreachable = data?.unreachable ?? false;
  const runningCount = agents.filter((a) => a.status === "running").length;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Card 1 — Active agents */}
      <Card className="lg:col-span-2">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-4 w-4" /> Active agents
              </CardTitle>
              <CardDescription>
                {loading
                  ? "Loading…"
                  : unreachable
                    ? "Backend unreachable"
                    : `${runningCount} running · ${agents.length} total`}
              </CardDescription>
            </div>
            {unreachable ? (
              <Badge variant="destructive">offline</Badge>
            ) : (
              <Badge variant="secondary">
                <Activity className="h-3 w-3 mr-1" /> live
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Polling /api/agents/active…
            </div>
          ) : agents.length === 0 ? (
            <div className="text-sm text-zinc-500">
              No active subagents. Start a pipeline run to populate this view.
            </div>
          ) : (
            <ul className="space-y-3">
              <AnimatePresence initial={false}>
                {agents.map((a) => (
                  <motion.li
                    key={a.id}
                    layout
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-mono text-xs text-zinc-400 truncate">{a.name}</div>
                        <div className="text-sm text-zinc-100 mt-0.5 line-clamp-2">
                          {a.currentTask || a.goal || "(no goal)"}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <Badge variant={statusVariant(a.status)}>{a.status}</Badge>
                        <span className="text-[10px] text-zinc-500">depth {a.depth}</span>
                      </div>
                    </div>
                    <dl className="mt-3 grid grid-cols-2 gap-y-1.5 gap-x-4 text-[11px]">
                      <dt className="text-zinc-500">Tool</dt>
                      <dd className="text-zinc-300 font-mono truncate">{a.toolCurrentlyInvoked}</dd>
                      <dt className="text-zinc-500">Sandbox</dt>
                      <dd className="text-zinc-300 font-mono truncate">{a.sandboxRuntime}</dd>
                      <dt className="text-zinc-500">Container</dt>
                      <dd className="text-zinc-300 font-mono truncate">{a.runtimeContainerId}</dd>
                      <dt className="text-zinc-500">Last activity</dt>
                      <dd className="text-zinc-300">{formatRelative(a.lastActivityTimestamp)}</dd>
                    </dl>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Card 2 — Sandbox runtime status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-4 w-4" /> Sandbox status
          </CardTitle>
          <CardDescription>Runtime health for the active session</CardDescription>
        </CardHeader>
        <CardContent>
          {session ? (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-zinc-500">Session</dt>
                <dd className="font-mono text-zinc-200 truncate max-w-[60%]">{session.id}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Status</dt>
                <dd>
                  <Badge variant={statusVariant(session.status)}>{session.status}</Badge>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Total tokens</dt>
                <dd className="font-mono text-zinc-200">{session.totalTokens.toLocaleString()}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Total cost</dt>
                <dd className="font-mono text-zinc-200">${session.totalCost.toFixed(4)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Started</dt>
                <dd className="text-zinc-300">{formatRelative(session.createdAt)}</dd>
              </div>
            </dl>
          ) : (
            <div className="text-sm text-zinc-500">No active session.</div>
          )}
        </CardContent>
      </Card>

      {/* Card 3 — Orchestration workflow state */}
      <Card className="lg:col-span-3">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Workflow className="h-4 w-4" /> Orchestration workflow
              </CardTitle>
              <CardDescription>
                mixin-based Agent → DelegateTaskTool → fan-out to leaf subagents
              </CardDescription>
            </div>
            <Badge variant="outline">
              {data?.toolCallsTotal ?? 0} tool calls
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
            <Stage label="Orchestrator" detail={`${runningCount} active`} state={runningCount > 0 ? "running" : "idle"} />
            <Stage label="Delegate" detail="delegate_task tool" state={agents.length > 0 ? "running" : "idle"} />
            <Stage label="Subagents" detail={`${agents.length} spawned`} state={agents.length > 0 ? "running" : "idle"} />
            <Stage label="Aggregator" detail="collect_results" state={session ? "armed" : "idle"} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Stage({ label, detail, state }: { label: string; detail: string; state: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="mt-1 text-zinc-100 font-medium">{detail}</div>
      <div className="mt-2">
        <Badge variant={statusVariant(state)}>{state}</Badge>
      </div>
    </div>
  );
}
