"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StatsCard } from "@/components/shared/StatsCard";
import {
  Activity,
  Server,
  TestTube,
  Cpu,
  CheckCircle2,
  Globe,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api/api-client";

type ProviderStatus = {
  provider: string;
  configured: boolean;
  model: string;
  has_key: boolean;
  base_url: string;
  api_mode?: string;
};

type MCPStatus = {
  name: string;
  transport: string;
  tools: number;
  connected: boolean;
};

type RunnerInfo = {
  id: string;
  name: string;
  language: string;
  framework: string;
  enabled: boolean;
};

function StatusBadge({ connected }: { connected: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800/50 text-zinc-300 border border-zinc-700/50">
      <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-400" : "bg-zinc-500"}`} />
      {connected ? "active" : "inactive"}
    </span>
  );
}

export default function InfraPage() {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPStatus[]>([]);
  const [runners, setRunners] = useState<RunnerInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [provData, mcpData, runData] = await Promise.all([
          api.get<ProviderStatus[]>("/api/settings/providers"),
          api.get<{ connections?: MCPStatus[] }>("/api/settings/mcp/connections"),
          api.get<{ runners?: RunnerInfo[] }>("/api/settings/runners"),
        ]);
        setProviders(Array.isArray(provData) ? provData : []);
        setMcpServers(mcpData?.connections ?? []);
        setRunners(runData?.runners ?? []);
      } catch {
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const connectedProviders = providers.filter((p) => p.has_key).length;
  const connectedMcp = mcpServers.filter((m) => m.connected).length;
  const activeRunners = runners.filter((r) => r.enabled).length;
  const totalMcp = mcpServers.length;

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatsCard icon={<Cpu size={16} />} label="LLM Providers" value={`${connectedProviders}/${providers.length}`} sub="with valid API keys" delay={0.05} />
        <StatsCard icon={<Server size={16} />} label="MCP Servers" value={`${connectedMcp}/${totalMcp}`} sub="active connections" delay={0.1} />
        <StatsCard icon={<TestTube size={16} />} label="Test Runners" value={String(activeRunners)} sub="enabled frameworks" delay={0.15} />
        <StatsCard icon={<Zap size={16} />} label="Pipeline" value="Auto" sub="mode active" delay={0.2} />
      </div>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-4">
            {[0, 1, 2].map((i) => <div key={i} className="h-24 rounded-2xl shimmer-bg border border-zinc-800/30" />)}
          </motion.div>
        ) : (
          <motion.div key="content" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className="space-y-6">
            <section>
              <div className="flex items-center gap-2 mb-4">
                <Globe size={14} className="text-zinc-500" />
                <h2 className="text-sm font-medium text-zinc-400 tracking-wide uppercase">LLM Providers</h2>
              </div>
              {providers.length === 0 ? (
                <div className="border border-dashed border-zinc-800 rounded-2xl p-8 text-center">
                  <p className="text-sm text-zinc-600">No providers configured.</p>
                </div>
              ) : (
                <div className="border border-zinc-800/50 rounded-2xl divide-y divide-zinc-800/30">
                  {providers.map((p) => (
                    <div key={p.provider} className="flex items-center justify-between px-5 py-3.5 hover:bg-zinc-900/30 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-sm font-medium text-zinc-200">{p.provider}</span>
                        <span className="text-xs text-zinc-500 font-mono truncate">{p.model}</span>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {p.base_url && <span className="text-xs text-zinc-600 font-mono hidden md:inline max-w-[180px] truncate">{p.base_url}</span>}
                        <StatusBadge connected={p.has_key} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section>
              <div className="flex items-center gap-2 mb-4">
                <Activity size={14} className="text-zinc-500" />
                <h2 className="text-sm font-medium text-zinc-400 tracking-wide uppercase">MCP Servers</h2>
              </div>
              {mcpServers.length === 0 ? (
                <div className="border border-dashed border-zinc-800 rounded-2xl p-8 text-center">
                  <p className="text-sm text-zinc-600">No MCP servers configured.</p>
                </div>
              ) : (
                <div className="border border-zinc-800/50 rounded-2xl divide-y divide-zinc-800/30">
                  {mcpServers.map((m) => (
                    <div key={m.name} className="flex items-center justify-between px-5 py-3.5 hover:bg-zinc-900/30 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-sm font-medium text-zinc-200">{m.name}</span>
                        <span className="text-xs text-zinc-600 font-mono">{m.transport}</span>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className="text-xs text-zinc-500">{m.tools} tool{m.tools !== 1 ? "s" : ""}</span>
                        <StatusBadge connected={m.connected} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section>
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 size={14} className="text-zinc-500" />
                <h2 className="text-sm font-medium text-zinc-400 tracking-wide uppercase">Test Runners</h2>
              </div>
              {runners.length === 0 ? (
                <div className="border border-dashed border-zinc-800 rounded-2xl p-8 text-center">
                  <p className="text-sm text-zinc-600">No test runners configured.</p>
                </div>
              ) : (
                <div className="border border-zinc-800/50 rounded-2xl divide-y divide-zinc-800/30">
                  {runners.slice(0, 10).map((r) => (
                    <div key={r.id} className="flex items-center justify-between px-5 py-3.5 hover:bg-zinc-900/30 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-sm font-medium text-zinc-200">{r.name}</span>
                        <span className="text-xs text-zinc-500 font-mono">{r.language}/{r.framework}</span>
                      </div>
                      <StatusBadge connected={r.enabled} />
                    </div>
                  ))}
                </div>
              )}
            </section>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
