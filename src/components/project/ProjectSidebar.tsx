"use client";

import { motion } from "framer-motion";
import {
  HeartPulse,
  DollarSign,
  ScrollText,
  ShieldCheck,
  TrendingDown,
  AlertTriangle,
  Crosshair,
  Clock,
  Webhook,
  Bell,
  Brain,
  Terminal,
  Puzzle,
  Plug,
  Bot,
  FlaskConical,
  LayoutDashboard,
  BarChart3,
  Cloud,
  Radio,
  Container,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface TabDef {
  id: string;
  label: string;
  icon: LucideIcon;
}

export interface TabGroup {
  label: string;
  tabs: TabDef[];
}

export const TAB_GROUPS: TabGroup[] = [
  {
    label: "Monitoring",
    tabs: [
      { id: "health", label: "Health", icon: HeartPulse },
      { id: "cost", label: "Cost", icon: DollarSign },
      { id: "logs", label: "Logs", icon: ScrollText },
    ],
  },
  {
    label: "AI OPS",
    tabs: [
      { id: "analytics", label: "Analytics", icon: BarChart3 },
      { id: "providers", label: "Providers", icon: Cloud },
      { id: "models", label: "Models", icon: DollarSign },
      { id: "memory", label: "Memory", icon: Brain },
      { id: "prompt", label: "Prompt", icon: Terminal },
      { id: "skills", label: "Skills", icon: Puzzle },
    ],
  },
  {
    label: "Infrastructure",
    tabs: [
      { id: "mcp", label: "MCP Servers", icon: Plug },
      { id: "channels", label: "Channels", icon: Radio },
      { id: "runners", label: "Runners", icon: Container },
    ],
  },
  {
    label: "Quality",
    tabs: [
      { id: "gates", label: "Gates", icon: ShieldCheck },
      { id: "regression", label: "Regression", icon: TrendingDown },
      { id: "flaky", label: "Flaky", icon: AlertTriangle },
      { id: "impact", label: "Impact", icon: Crosshair },
    ],
  },
  {
    label: "Automation",
    tabs: [
      { id: "cron", label: "Cron", icon: Clock },
      { id: "hooks", label: "Hooks", icon: Webhook },
      { id: "alerts", label: "Alerts", icon: Bell },
    ],
  },
  {
    label: "Workspace",
    tabs: [
      { id: "agents", label: "Agents", icon: Bot },
      { id: "experiments", label: "Experiments", icon: FlaskConical },
      { id: "custom", label: "Custom Dashboards", icon: LayoutDashboard },
    ],
  },
];

const allTabs = TAB_GROUPS.flatMap((g) => g.tabs);

interface ProjectSidebarProps {
  activeTab: string;
  onTabChange: (id: string) => void;
}

export function ProjectSidebar({ activeTab, onTabChange }: ProjectSidebarProps) {
  return (
    <div className="space-y-5">
      {TAB_GROUPS.map((group) => (
        <div key={group.label}>
          <div className="text-[10px] font-medium uppercase tracking-wider text-neutral-600 mb-1.5 px-1">
            {group.label}
          </div>

          {/* Settings-style pill bar */}
          <div className="flex flex-col gap-0.5">
            {group.tabs.map((tab, i) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <motion.button
                  key={tab.id}
                  onClick={() => onTabChange(tab.id)}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.02, type: "spring", stiffness: 120, damping: 18 }}
                  className={cn(
                    "flex items-center gap-2 rounded-[1rem] text-xs font-medium tracking-tight px-3 py-1.5 transition-all whitespace-nowrap active:scale-[0.95] text-left",
                    isActive
                      ? "bg-white/[0.08] text-neutral-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                      : "text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.03]"
                  )}
                >
                  <Icon className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
                  <span>{tab.label}</span>
                </motion.button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
