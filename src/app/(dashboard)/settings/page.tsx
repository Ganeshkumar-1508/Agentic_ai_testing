"use client";

export const dynamic = "force-dynamic";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Download, FileText, type LucideIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PageHeader } from "@/components/shared/PageHeader";
import { BackendProvidersSettings } from "@/components/settings/BackendProvidersSettings";
import { PipelineModelAssignment } from "@/components/settings/PipelineModelAssignment";
import { MCPServerManager } from "@/components/settings/MCPServerManager";
import { WebhookConfig } from "@/components/settings/WebhookConfig";
import { CICDSetup } from "@/components/settings/CICDSetup";
import { SessionBrowser } from "@/components/settings/SessionBrowser";
import { AllowlistManager } from "@/components/agents/AllowlistManager";
import { PlatformAdapterSettings } from "@/components/settings/PlatformAdapterSettings";
import { DigestConfigPanel } from "@/components/settings/DigestConfigPanel";
import { EnvVarsManager } from "@/components/settings/EnvVarsManager";
import { NotificationPreferences } from "@/components/settings/NotificationPreferences";
import { EscalationPolicySettings } from "@/components/settings/EscalationPolicySettings";
import { FeatureFlags } from "@/components/settings/FeatureFlags";
import { IntegrationSettings } from "@/components/settings/IntegrationSettings";
import { SearchProvidersSettings } from "@/components/settings/SearchProvidersSettings";
import { OTelSettings } from "@/components/settings/OTelSettings";
import { ToolPermissionsManager } from "@/components/settings/ToolPermissionsManager";
import { BudgetSettings } from "@/components/settings/BudgetSettings";
import { ObservabilitySettings } from "@/components/settings/ObservabilitySettings";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import {
  Cpu, Puzzle, Webhook as WebhookIcon, GitBranch, History, BookOpen,
  MessageSquare, Gauge, Variable, Bell, Flag, DollarSign,
  Bot, Sliders, PuzzleIcon, Shield, Activity, Radio, Search,
} from "lucide-react";
import React from "react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

type TabDef = { id: string; label: string; icon: LucideIcon; desc: string };
type TabGroup = { label: string; description: string; tabs: TabDef[] };

const TAB_GROUPS: TabGroup[] = [
  {
    label: "Agents",
    description: "Define agents, manage skills, and gate tool access",
    tabs: [
      { id: "agents", label: "Agent Definitions", icon: Bot, desc: "Create, edit, and delete subagent definitions used by the pipeline" },
      { id: "tool-perms", label: "Tool Permissions", icon: Shield, desc: "Control which tools each agent can access (allow, ask, deny)" },
      { id: "prompts", label: "Prompts", icon: FileText, desc: "Manage system prompts for each agent role" },
    ],
  },
  {
    label: "Pipeline",
    description: "Runners, gates, CI/CD hooks, and model assignment",
    tabs: [
      { id: "ci", label: "CI/CD", icon: GitBranch, desc: "Connect to GitHub, GitLab, or Bitbucket for auto-triggered pipelines" },
      { id: "models", label: "Model Assignment", icon: Sliders, desc: "Assign LLM models per agent role or task type" },
    ],
  },
  {
    label: "Integrations",
    description: "LLM providers, MCP servers, webhooks, delivery channels",
    tabs: [
      { id: "backend", label: "LLM Providers", icon: Cpu, desc: "Add and configure LLM providers (OpenAI, Anthropic, OpenCode, etc.)" },
      { id: "mcp", label: "MCP Servers", icon: Puzzle, desc: "Manage Model Context Protocol servers for extended tool access" },
      { id: "webhooks", label: "Webhooks", icon: WebhookIcon, desc: "Configure incoming/outgoing webhooks for event-driven automation" },
      { id: "integrations", label: "External Services", icon: PuzzleIcon, desc: "Connect Slack, Linear, Jira, Sentry, and other services" },
      { id: "platforms", label: "Delivery Platforms", icon: MessageSquare, desc: "Configure Slack, Teams, Telegram, and email delivery channels" },
      { id: "plugins", label: "Plugins", icon: Puzzle, desc: "Manage installed plugins and hook registrations" },
      { id: "search", label: "Search Providers", icon: Search, desc: "Configure web search backends (Tavily, Firecrawl, Jina AI)" },
    ],
  },
  {
    label: "System",
    description: "Environment, budgets, notifications, advanced",
    tabs: [
      { id: "environment", label: "Environment", icon: Variable, desc: "Manage environment variables injected into sandbox containers" },
      { id: "budgets", label: "Cost & Budgets", icon: DollarSign, desc: "Set token and cost budgets per agent, phase, and run" },
      { id: "observability", label: "Observability", icon: Activity, desc: "OpenTelemetry tracing configuration" },
      { id: "notifications", label: "Notifications", icon: Bell, desc: "Configure alert channels for pipeline events and failures" },
      { id: "digest", label: "Daily Digest", icon: Radio, desc: "Schedule automated daily summary reports" },
      { id: "runner", label: "Runner", icon: Cpu, desc: "Configure sandbox size, timeouts, and resource limits for test runners" },
      { id: "flags", label: "Feature Flags", icon: Flag, desc: "Toggle experimental features on/off" },
      { id: "permissions", label: "Access Control", icon: Shield, desc: "Manage allowlists and access policies for API keys" },
      { id: "escalation", label: "Escalation", icon: Shield, desc: "Configure when agents escalate to humans" },
      { id: "routing", label: "Model Routing", icon: Cpu, desc: "Route tasks to different models by task type" },
      { id: "privacy", label: "Data & Privacy", icon: Shield, desc: "Data retention, export, and privacy controls" },
    ],
  },
];

const PANEL_MAP: Record<string, React.FC> = {
  agents: () => {
    const AgentsComp = React.lazy(() => import("@/components/settings/AgentsSettings").then(m => ({ default: m.AgentsSettings })));
    return (
      <ErrorBoundary fallback={<div className="text-sm text-red-400 p-6 border border-red-400/20 rounded-xl">Failed to load Agents</div>}>
        <React.Suspense fallback={<div className="text-sm text-zinc-500 p-6 animate-pulse">Loading agents...</div>}>
          <AgentsComp />
        </React.Suspense>
      </ErrorBoundary>
    );
  },
  backend: () => (
    <div className="space-y-5">
      <BackendProvidersSettings key="backend-providers" />
      <PipelineModelAssignment />
    </div>
  ),
  mcp: MCPServerManager,
  platforms: PlatformAdapterSettings,
  models: () => {
    const ModelsPanel = React.lazy(() => import("@/components/project/panels/ModelsPanel").then(m => ({ default: m.ModelsPanel })));
    return (
      <ErrorBoundary fallback={<div className="text-sm text-red-400 p-6 border border-red-400/20 rounded-xl">Failed to load Models panel</div>}>
        <React.Suspense fallback={<div className="text-sm text-zinc-500 p-6 animate-pulse">Loading models...</div>}>
          <ModelsPanel />
        </React.Suspense>
      </ErrorBoundary>
    );
  },
  webhooks: WebhookConfig,
  ci: CICDSetup,
  prompts: () => {
    const PromptPanel = React.lazy(() => import("@/components/project/panels/PromptPanel").then(m => ({ default: m.PromptPanel })));
    return (
      <ErrorBoundary fallback={<div className="text-sm text-red-400 p-6 border border-red-400/20 rounded-xl">Failed to load Prompts panel</div>}>
        <React.Suspense fallback={<div className="text-sm text-zinc-500 p-6 animate-pulse">Loading prompts...</div>}>
          <PromptPanel />
        </React.Suspense>
      </ErrorBoundary>
    );
  },
  digest: DigestConfigPanel,
  permissions: () => <AllowlistManager />,
  environment: EnvVarsManager,
  notifications: NotificationPreferences,
  runner: () => {
    const RunnerComp = React.lazy(() => import("@/components/settings/RunnerConfigSettings").then(m => ({ default: m.RunnerConfigSettings })));
    return (
      <ErrorBoundary fallback={<div className="text-sm text-red-400 p-6 border border-red-400/20 rounded-xl">Failed to load</div>}>
        <React.Suspense fallback={<div className="text-sm text-zinc-500 p-6 animate-pulse">Loading...</div>}>
          <RunnerComp />
        </React.Suspense>
      </ErrorBoundary>
    );
  },
  flags: FeatureFlags,
  escalation: EscalationPolicySettings,
  routing: () => {
    const RoutingPanel = React.lazy(() => import("@/components/settings/ModelRoutingSettings").then(m => ({ default: m.ModelRoutingSettings })));
    return (
      <ErrorBoundary fallback={<div className="text-sm text-red-400 p-6 border border-red-400/20 rounded-xl">Failed to load</div>}>
        <React.Suspense fallback={<div className="text-sm text-zinc-500 p-6 animate-pulse">Loading...</div>}>
          <RoutingPanel />
        </React.Suspense>
      </ErrorBoundary>
    );
  },
  privacy: () => {
    const PrivacyPanel = React.lazy(() => import("@/components/settings/DataPrivacySettings").then(m => ({ default: m.DataPrivacySettings })));
    return (
      <ErrorBoundary fallback={<div className="text-sm text-red-400 p-6 border border-red-400/20 rounded-xl">Failed to load</div>}>
        <React.Suspense fallback={<div className="text-sm text-zinc-500 p-6 animate-pulse">Loading...</div>}>
          <PrivacyPanel />
        </React.Suspense>
      </ErrorBoundary>
    );
  },
  plugins: () => {
    const PluginsPanel = React.lazy(() => import("@/components/settings/PluginManagerSettings").then(m => ({ default: m.PluginManagerSettings })));
    return (
      <ErrorBoundary fallback={<div className="text-sm text-red-400 p-6 border border-red-400/20 rounded-xl">Failed to load</div>}>
        <React.Suspense fallback={<div className="text-sm text-zinc-500 p-6 animate-pulse">Loading...</div>}>
          <PluginsPanel />
        </React.Suspense>
      </ErrorBoundary>
    );
  },
  integrations: IntegrationSettings,
  otel: OTelSettings,
  search: SearchProvidersSettings,
  "tool-perms": ToolPermissionsManager,
  budgets: BudgetSettings,
  observability: ObservabilitySettings,
};

const allTabs = TAB_GROUPS.flatMap((g) => g.tabs);
const firstTabId = TAB_GROUPS[0].tabs[0].id;

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
};

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
};

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-zinc-500 animate-pulse">Loading settings…</div>}>
      <SettingsPageInner />
    </Suspense>
  );
}

function SettingsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const urlTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<string>(
    urlTab && allTabs.some((t) => t.id === urlTab) ? urlTab : firstTabId
  );
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    const t = searchParams.get("tab");
    if (t && allTabs.some((x) => x.id === t) && t !== activeTab) {
      setActiveTab(t);
    }
  }, [searchParams, activeTab]);

  const handleTabChange = useCallback(
    (id: string) => {
      setActiveTab(id);
      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", id);
      router.replace(`/settings?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const data = await api.get<unknown>("/api/export/all");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `testai-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Settings exported");
    } catch {
      toast.error("Export failed");
    }
    setExporting(false);
  }, []);

  const currentTab = allTabs.find((t) => t.id === activeTab);
  const currentGroup = TAB_GROUPS.find((g) => g.tabs.some((t) => t.id === activeTab));
  const ActivePanel = PANEL_MAP[activeTab];

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={item} className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <PageHeader
            title={currentGroup?.label ?? "Settings"}
            description={
              currentGroup
                ? currentGroup.description
                : "Tune the platform to match your team's workflow"
            }
          />
        </div>
        <motion.button
          variants={item}
          onClick={handleExport}
          disabled={exporting}
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.98 }}
          className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-[12px] font-medium bg-white/[0.03] border border-white/[0.06] text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-200 transition-colors disabled:opacity-40 shrink-0"
        >
          <Download className="w-3.5 h-3.5" strokeWidth={1.5} />
          {exporting ? "Exporting…" : "Export All"}
        </motion.button>
      </motion.div>

      <motion.div variants={item}>
        <div className="overflow-x-auto -mx-2 px-2 pb-1">
          <div className="inline-flex items-center gap-1 bg-card border border-white/[0.06] rounded-[1.5rem] p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            {TAB_GROUPS.map((group) => {
              const hasActive = group.tabs.some((t) => t.id === activeTab);
              return (
                <DropdownMenu key={group.label}>
                  <DropdownMenuTrigger asChild>
                    <button
                      className={cn(
                        "group inline-flex items-center gap-1.5 rounded-[1rem] text-xs px-3 py-1.5 transition-all whitespace-nowrap active:scale-[0.95]",
                        hasActive
                          ? "bg-emerald-500/10 text-emerald-400 shadow-[inset_0_1px_0_rgba(52,211,153,0.06)]"
                          : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30"
                      )}
                    >
                      <ChevronDown
                        size={11}
                        strokeWidth={2}
                        className="shrink-0 transition-transform duration-200 group-data-[state=open]:rotate-180"
                      />
                      <span className="font-medium tracking-tight">{group.label}</span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-zinc-800/40 text-zinc-600 font-medium leading-none">
                        {group.tabs.length}
                      </span>
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="start"
                    sideOffset={6}
                    className="min-w-[200px] bg-popover border-zinc-800/50 rounded-xl p-1.5 shadow-[0_12px_32px_-8px_rgba(0,0,0,0.5)]"
                  >
                    {group.tabs.map((tab) => {
                      const Icon = tab.icon;
                      const isActive = activeTab === tab.id;
                      return (
                        <DropdownMenuItem
                          key={tab.id}
                          onClick={() => handleTabChange(tab.id)}
                          className={cn(
                            "flex items-center gap-2 rounded-[0.75rem] text-xs px-2.5 py-1.5 cursor-pointer transition-all",
                            isActive
                              ? "bg-emerald-500/10 text-emerald-400 focus:bg-emerald-500/10 focus:text-emerald-400"
                              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30 focus:bg-zinc-800/30 focus:text-zinc-200"
                          )}
                        >
                          <Icon className="w-3.5 h-3.5 shrink-0 opacity-60" strokeWidth={1.5} />
                          <span className="font-medium tracking-tight">{tab.label}</span>
                          {isActive && (
                            <span className="ml-auto w-1.5 h-1.5 rounded-full bg-emerald-400/80 shrink-0" />
                          )}
                        </DropdownMenuItem>
                      );
                    })}
                  </DropdownMenuContent>
                </DropdownMenu>
              );
            })}
          </div>
        </div>
      </motion.div>

      <motion.div variants={item} className="flex items-center gap-2 text-[11px] font-mono text-zinc-600 -mt-3">
        <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-zinc-500">
          {activeTab}
        </span>
        {currentTab && (
          <span className="text-zinc-700">·</span>
        )}
        {currentTab && (
          <span className="truncate max-w-[60ch]">{currentTab.desc}</span>
        )}
      </motion.div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
          {currentTab && ActivePanel ? (
            <ActivePanel />
          ) : (
            <div className="text-sm text-zinc-600 p-6">Select a setting</div>
          )}
        </motion.div>
      </AnimatePresence>
    </motion.div>
  );
}
