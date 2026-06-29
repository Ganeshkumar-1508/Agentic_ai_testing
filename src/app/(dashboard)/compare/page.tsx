"use client";

import { Suspense, useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { GitCompare } from "lucide-react";
import { RunComparison } from "@/components/agents/RunComparison";
import { SessionReplay } from "@/components/pipeline/SessionReplay";
import { api } from "@/lib/api/api-client";

function ComparePageInner() {
  const [runA, setRunA] = useState("");
  const [runB, setRunB] = useState("");
  const [activeTab, setActiveTab] = useState<"compare" | "replay">("compare");
  const [replayId, setReplayId] = useState("");

  const { data: runs } = useQuery({
    queryKey: ["recent-runs"],
    queryFn: async () => {
      return api.get<{ runs?: any[] }>(`/api/runs?limit=20`);
    },
  });

  const runList = (runs?.runs ?? []) as any[];

  return (
    <div className="max-w-7xl mx-auto px-8 pt-6 pb-12 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">/compare</div>
          <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Run Analysis</h1>
          <p className="text-[13px] text-zinc-500 mt-0.5">Compare runs and replay agent sessions</p>
        </div>
        <div className="flex bg-card border border-white/[0.06] rounded-full p-0.5 gap-0.5">
          <button onClick={() => setActiveTab("compare")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all ${
              activeTab === "compare" ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-500 hover:text-zinc-300"
            }`}>
            <GitCompare className="w-3 h-3" strokeWidth={1.5} /> Compare
          </button>
          <button onClick={() => setActiveTab("replay")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all ${
              activeTab === "replay" ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-500 hover:text-zinc-300"
            }`}>
            <svg className="w-3 h-3" strokeWidth={1.5} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> Replay
          </button>
        </div>
      </div>

      {activeTab === "compare" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[9px] text-zinc-600 uppercase tracking-wider mb-1.5 block">Run A</label>
              <select value={runA} onChange={(e) => setRunA(e.target.value)}
                className="w-full bg-card border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30">
                <option value="">Select a run...</option>
                {runList.map((r: any) => (
                  <option key={r.id} value={r.id}>{r.id?.slice(0, 12)} — {r.status} ({r.testCount || 0} tests)</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[9px] text-zinc-600 uppercase tracking-wider mb-1.5 block">Run B</label>
              <select value={runB} onChange={(e) => setRunB(e.target.value)}
                className="w-full bg-card border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30">
                <option value="">Select a run...</option>
                {runList.map((r: any) => (
                  <option key={r.id} value={r.id}>{r.id?.slice(0, 12)} — {r.status} ({r.testCount || 0} tests)</option>
                ))}
              </select>
            </div>
          </div>
          {runA && (
            <RunComparison runId={runA} compareId={runB || null} onClose={() => { setRunA(""); setRunB(""); }} />
          )}
        </div>
      )}

      {activeTab === "replay" && (
        <div className="space-y-4">
          <div>
            <label className="text-[9px] text-zinc-600 uppercase tracking-wider mb-1.5 block">Session ID</label>
            <div className="flex gap-2">
              <input value={replayId} onChange={(e) => setReplayId(e.target.value)}
                placeholder="Enter a session ID to replay..."
                className="flex-1 bg-card border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 placeholder-zinc-700 outline-none focus:border-emerald-500/30 font-mono" />
            </div>
          </div>
          <ReplayView sessionId={replayId} />
        </div>
      )}
    </div>
  );
}

function ReplayView({ sessionId }: { sessionId: string }) {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!sessionId.trim()) { setEvents([]); return; }
    setLoading(true);
    setError("");
    api.get<{ messages?: any[] }>(`/api/sessions/${encodeURIComponent(sessionId.trim())}`)
      .then((data) => {
        if (data.messages) setEvents(data.messages);
        else setEvents([]);
      })
      .catch((e) => { setError(String(e)); setEvents([]); })
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (!sessionId.trim()) return null;
  if (loading) return <div className="py-12 text-center text-sm text-zinc-600">Loading session...</div>;
  if (error) return <div className="py-12 text-center text-sm text-red-400">{error}</div>;
  if (events.length === 0) return <div className="py-12 text-center text-sm text-zinc-600">No events found</div>;
  return <SessionReplay events={events} isLoading={false} />;
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] flex items-center justify-center bg-background"><div className="flex items-center gap-3 text-zinc-600"><GitCompare className="w-4 h-4 animate-spin" strokeWidth={1.5} /><span className="text-sm">Loading...</span></div></div>}>
      <ComparePageInner />
    </Suspense>
  );
}
