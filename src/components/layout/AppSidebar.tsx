"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  Bot,
  Beaker,
  Settings,
  GitBranch,
  ChevronLeft,
  ChevronRight,
  Clock,
  Columns3,
  Gauge,
  GitCompare,
  Shield,
  FileBox,
  Box,
  Cpu,
  ListChecks,
  Radio,
  Briefcase,
  Activity,
  Network,
  DollarSign,
  Target,
  Bell,
  Search,
} from "lucide-react";
import { BackendStatus } from "@/components/shared/BackendStatus";
import { MCPStatus } from "@/components/shared/MCPStatus";
import { ApprovalBadge } from "@/components/shared/ApprovalBadge";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { cn } from "@/lib/utils";

function CollapsibleSection({
  label,
  open,
  onToggle,
  collapsed,
  children,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  collapsed: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-1">
      <button
        onClick={onToggle}
        className={cn(
          "flex items-center gap-1.5 w-full px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.8px] transition-colors",
          collapsed
            ? "justify-center px-0 h-6"
            : "text-zinc-600 hover:text-zinc-400"
        )}
        title={collapsed ? label : undefined}
      >
        {collapsed ? null : <span className="flex-1 text-left">{label}</span>}
      </button>
      <AnimatePresence initial={false}>
        {open && !collapsed && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="space-y-0.5 mt-0.5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const NAV_CATEGORIES = [
  {
    label: "Core",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Chat", href: "/chat", icon: Bot },
      { label: "Agents", href: "/agents", icon: Bot },
      { label: "Skills", href: "/skills", icon: Bot },
      { label: "Pipeline", href: "/pipeline", icon: Activity },
      { label: "Sessions", href: "/sessions", icon: Clock },
      { label: "Knowledge Graph", href: "/knowledge-graph", icon: Network },
      { label: "Jobs", href: "/jobs", icon: Briefcase },
      { label: "Workflows", href: "/workflows", icon: GitBranch },
      { label: "Observability", href: "/observability", icon: Gauge },
      { label: "Audit", href: "/audit", icon: Search },
      { label: "Cost", href: "/cost", icon: DollarSign },
      { label: "Evaluate", href: "/evaluate", icon: Target },
    ],
  },
  {
    label: "Testing",
    items: [
      { label: "Test Cases", href: "/test-cases", icon: Beaker },
      { label: "Requirements", href: "/requirements", icon: ListChecks },
      { label: "Quality", href: "/quality", icon: Gauge },
      { label: "Traceability", href: "/traceability", icon: GitBranch },
    ],
  },
  {
    label: "Agent",
    items: [
      { label: "Kanban", href: "/kanban", icon: Columns3 },
      { label: "Compare Runs", href: "/compare", icon: GitCompare },
      { label: "Pull Requests", href: "/pull-requests", icon: GitBranch },
      { label: "Activity", href: "/activity", icon: Radio },
    ],
  },
  {
    label: "Infra",
    items: [
      { label: "Sandbox", href: "/sandbox", icon: Box },
      { label: "AI Ops", href: "/ai-ops", icon: Cpu },
      { label: "Artifacts", href: "/artifacts", icon: FileBox },
    ],
  },
  {
    label: "Config",
    items: [
      { label: "Settings", href: "/settings", icon: Settings },
      { label: "Notifications", href: "/notifications", icon: Bell },
      { label: "Admin", href: "/admin", icon: Shield },
    ],
  },
];

const STORAGE_KEY = "sidebarCollapsed";
const SECTIONS_KEY = "sidebarSections";

function readPersistedCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(STORAGE_KEY) === "true";
}

function readPersistedSections(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(SECTIONS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export default function AppSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [sectionOpen, setSectionOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setCollapsed(readPersistedCollapsed());
    setSectionOpen(readPersistedSections());
  }, []);

  useEffect(() => {
    const onToggle = () => {
      setCollapsed((prev) => {
        const next = !prev;
        if (typeof window !== "undefined") {
          window.localStorage.setItem(STORAGE_KEY, String(next));
        }
        return next;
      });
    };
    window.addEventListener("toggle:sidebar", onToggle);
    return () => window.removeEventListener("toggle:sidebar", onToggle);
  }, []);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, String(next));
    }
  };

  const persistSections = (next: Record<string, boolean>) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SECTIONS_KEY, JSON.stringify(next));
    }
  };

  const toggleSection = (label: string) => {
    setSectionOpen((prev) => {
      const next = { ...prev, [label]: !prev[label] };
      persistSections(next);
      return next;
    });
  };

  // Auto-open the active section whenever the route changes. The user's
  // explicit toggle wins until they navigate into a different section.
  useEffect(() => {
    setSectionOpen((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const cat of NAV_CATEGORIES) {
        const isActive = cat.items.some(
          (item) => pathname === item.href || pathname.startsWith(item.href + "/"),
        );
        if (isActive) {
          if (next[cat.label] === false) {
            // User explicitly closed this section; respect that.
            continue;
          }
          if (next[cat.label] !== true) {
            next[cat.label] = true;
            changed = true;
          }
        }
      }
      return changed ? next : prev;
    });
  }, [pathname]);

  // Group-level navigation: clicking a collapsed group navigates to its
  // "home" item (first entry) and shows a popover with the rest.
  const [openPopover, setOpenPopover] = useState<string | null>(null);

  return (
    <motion.aside
      className="min-h-[100dvh] overflow-hidden sticky top-0 flex flex-col bg-sidebar border-r border-border relative shrink-0"
      animate={{ width: collapsed ? 60 : 256 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
    >
      <div
        className={cn(
          "flex items-center gap-3 border-b border-border shrink-0 px-3 py-3.5 bg-sidebar/60 backdrop-blur-md",
          collapsed && "justify-center"
        )}
      >
        <button
          onClick={toggle}
          className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.04] transition-colors shrink-0"
          title={collapsed ? "Expand sidebar (⌘B)" : "Collapse sidebar (⌘B)"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
          ) : (
            <ChevronLeft className="w-4 h-4" strokeWidth={1.5} />
          )}
        </button>
        <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-400">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              key="brand"
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: "auto" }}
              exit={{ opacity: 0, width: 0 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
              className="flex items-baseline gap-2 overflow-hidden whitespace-nowrap"
            >
              <span className="text-foreground font-semibold text-sm tracking-tight">TestAI</span>
              <span className="text-[9px] font-medium text-muted-foreground uppercase tracking-wider bg-muted px-1.5 py-0.5 rounded">
                beta
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {NAV_CATEGORIES.map((cat, catIdx) => {
          const catActive = cat.items.some(
            (item) => pathname === item.href || pathname.startsWith(item.href + "/"),
          );
          const open = collapsed ? true : sectionOpen[cat.label] ?? catActive;
          if (collapsed) {
            const LeadIcon = cat.items[0].icon;
            const popoverOpen = openPopover === cat.label;
            return (
              <div key={cat.label} className={cn("relative", catIdx > 0 && "mt-3 pt-3 border-t border-white/[0.04]")}>
                <button
                  type="button"
                  onClick={() => setOpenPopover(popoverOpen ? null : cat.label)}
                  onBlur={() => setTimeout(() => setOpenPopover(null), 150)}
                  className={cn(
                    "relative w-full flex items-center justify-center px-2 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 active:scale-[0.98]",
                    catActive
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "text-sidebar-foreground hover:text-foreground hover:bg-muted"
                  )}
                  title={cat.label}
                  aria-label={cat.label}
                  aria-expanded={popoverOpen}
                >
                  <LeadIcon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                  {catActive && (
                    <span className="absolute right-1.5 top-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.6)]" />
                  )}
                </button>
                <AnimatePresence>
                  {popoverOpen && (
                    <motion.div
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -6 }}
                      transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
                      className="absolute left-full top-0 ml-2 z-50 min-w-[200px] py-1.5 rounded-xl bg-zinc-900/95 backdrop-blur-md border border-white/[0.06] shadow-[0_8px_32px_-8px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.04)]"
                    >
                      <div className="px-3 py-1.5 text-[9px] font-semibold uppercase tracking-[0.8px] text-zinc-600">
                        {cat.label}
                      </div>
                      {cat.items.map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname === item.href;
                        return (
                          <Link
                            key={item.href}
                            href={item.href}
                            onClick={() => setOpenPopover(null)}
                            className={cn(
                              "flex items-center gap-2.5 px-3 py-1.5 mx-1 rounded-lg text-[12.5px] transition-colors",
                              isActive
                                ? "bg-emerald-500/10 text-emerald-400"
                                : "text-zinc-300 hover:text-zinc-100 hover:bg-white/[0.04]"
                            )}
                          >
                            <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                            <span className="whitespace-nowrap">{item.label}</span>
                          </Link>
                        );
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          }
          return (
            <div key={cat.label} className={catIdx > 0 ? "mt-3 pt-3 border-t border-white/[0.04]" : ""}>
              <CollapsibleSection
                label={cat.label}
                open={!!open}
                onToggle={() => toggleSection(cat.label)}
                collapsed={false}
              >
                {cat.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 active:scale-[0.98]",
                        isActive
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "text-sidebar-foreground hover:text-foreground hover:bg-muted"
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                      <span className="whitespace-nowrap">{item.label}</span>
                    </Link>
                  );
                })}
              </CollapsibleSection>
            </div>
          );
        })}
      </nav>

      <div className="shrink-0 overflow-hidden">
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              key="footer"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="space-y-2"
            >
              <div className="px-4 pt-2"><ApprovalBadge /></div>
              <MCPStatus />
              <BackendStatus />
              <div className="px-4 pb-3"><ThemeToggle /></div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.aside>
  );
}
