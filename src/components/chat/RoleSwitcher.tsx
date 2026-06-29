"use client";

import { useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Users, Code2, Search, BookOpen, Wrench, Terminal, FileText, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

export interface RoleOption {
  id: string;
  label: string;
  description: string;
  icon: "bot" | "code" | "search" | "book" | "wrench" | "terminal" | "file";
}

const ROLE_PRESETS: RoleOption[] = [
  { id: "general", label: "General Purpose", description: "Read, write, search, execute. Best for most tasks.", icon: "bot" },
  { id: "code-expert", label: "Code Architect", description: "Deep code analysis. Read-only, no mutations.", icon: "code" },
  { id: "researcher", label: "Researcher", description: "Web research and content extraction.", icon: "search" },
  { id: "data-analyst", label: "Data Analyst", description: "Run code, query databases, analyze data.", icon: "terminal" },
  { id: "devops", label: "DevOps / SRE", description: "Infrastructure automation, Docker, shell scripts.", icon: "wrench" },
  { id: "writer", label: "Documentation", description: "Read codebases, write markdown and documentation.", icon: "file" },
];

const ROLE_ICONS: Record<string, React.ElementType> = {
  bot: Bot,
  code: Code2,
  search: Search,
  book: BookOpen,
  wrench: Wrench,
  terminal: Terminal,
  file: FileText,
};

interface RoleSwitcherProps {
  currentRole: string;
  onRoleChange: (roleId: string) => void;
  disabled?: boolean;
}

export function RoleSwitcher({ currentRole, onRoleChange, disabled }: RoleSwitcherProps) {
  const [open, setOpen] = useState(false);

  const current = useMemo(
    () => ROLE_PRESETS.find((r) => r.id === currentRole) || ROLE_PRESETS[0],
    [currentRole]
  );

  const handleSelect = useCallback((id: string) => {
    onRoleChange(id);
    setOpen(false);
  }, [onRoleChange]);

  const CurrentIcon = ROLE_ICONS[current.icon] || Bot;

  return (
    <div className="relative">
      <button
        type="button"
        className={cn(
          "agent-meta-chip flex items-center gap-1.5",
          disabled && "opacity-40 cursor-not-allowed"
        )}
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        title={`Role: ${current.label}`}
      >
        <span className="agent-chip-icon">
          <CurrentIcon width={11} height={11} strokeWidth={1.5} />
        </span>
        <span className="text-[10px] max-w-[80px] truncate">{current.label}</span>
        <ChevronDown className="agent-chev" width={9} height={9} strokeWidth={2.5} />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40"
              onClick={() => setOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, y: -4, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.96 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="absolute bottom-full left-0 mb-1 z-50 w-64 rounded-xl bg-zinc-900/95 backdrop-blur-md border border-zinc-800/60 shadow-[0_8px_32px_-8px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.04)] overflow-hidden"
            >
              <div className="px-3 py-2 text-[9px] font-semibold uppercase tracking-[0.8px] text-zinc-600 border-b border-zinc-800/30">
                Agent Role
              </div>
              <div className="p-1 space-y-0.5">
                {ROLE_PRESETS.map((role) => {
                  const RoleIcon = ROLE_ICONS[role.icon] || Bot;
                  const isActive = role.id === currentRole;
                  return (
                    <button
                      key={role.id}
                      onClick={() => handleSelect(role.id)}
                      className={cn(
                        "w-full flex items-start gap-2.5 px-3 py-2 rounded-lg text-left transition-all duration-200 active:scale-[0.98]",
                        isActive
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "text-zinc-300 hover:bg-zinc-800/40 hover:text-zinc-100"
                      )}
                    >
                      <div className={cn(
                        "w-7 h-7 rounded-lg flex items-center justify-center mt-0.5",
                        isActive ? "bg-emerald-500/15" : "bg-zinc-800/50"
                      )}>
                        <RoleIcon size={12} className={isActive ? "text-emerald-400" : "text-zinc-500"} strokeWidth={1.5} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium">{role.label}</div>
                        <div className="text-[10px] text-zinc-600 mt-0.5 line-clamp-2">{role.description}</div>
                      </div>
                      {isActive && (
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-2 shrink-0 shadow-[0_0_4px_rgba(52,211,153,0.6)]" />
                      )}
                    </button>
                  );
                })}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
