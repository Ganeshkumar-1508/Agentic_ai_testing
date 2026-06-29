"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Folder, Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

export type ProjectSummary = {
  project_id: string;
  requirement_count: number;
  test_count: number;
  passed_count: number;
  coverage_pct: number;
  is_default: boolean;
};

const STORAGE_KEY = "testai.activeProjectId";

export function useActiveProject(): [string, (id: string) => void] {
  const [active, setActive] = useState<string>("default");
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setActive(stored);
  }, []);
  const update = (id: string) => {
    setActive(id);
    localStorage.setItem(STORAGE_KEY, id);
    window.dispatchEvent(new CustomEvent("testai:active-project-changed", { detail: id }));
  };
  return [active, update];
}

export function useActiveProjectId(): string {
  const [id, setId] = useState<string>("default");
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setId(stored);
    const handler = (e: Event) => setId((e as CustomEvent<string>).detail);
    window.addEventListener("testai:active-project-changed", handler);
    const storageHandler = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) setId(e.newValue);
    };
    window.addEventListener("storage", storageHandler);
    return () => {
      window.removeEventListener("testai:active-project-changed", handler);
      window.removeEventListener("storage", storageHandler);
    };
  }, []);
  return id;
}

export function useProjects() {
  return useQuery<{ projects: ProjectSummary[] }>({
    queryKey: ["projects"],
    queryFn: () => api.get<{ projects: ProjectSummary[] }>(`/api/projects`),
    refetchInterval: 60_000,
  });
}

export function ProjectPicker() {
  const [active, setActive] = useActiveProject();
  const { data, isLoading } = useProjects();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const projects = data?.projects ?? [];
  const current = projects.find((p) => p.project_id === active) ?? projects[0];

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 pl-2.5 pr-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.1] transition-colors"
      >
        <Folder className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
        <span className="text-[11px] font-mono text-neutral-500 uppercase tracking-wider">project</span>
        <span className="text-[12px] font-medium text-neutral-100 max-w-[140px] truncate">
          {isLoading ? "…" : current?.project_id ?? "default"}
        </span>
        <ChevronDown
          className={cn(
            "w-3 h-3 text-neutral-500 transition-transform",
            open && "rotate-180"
          )}
          strokeWidth={2}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] as const }}
            className="absolute right-0 top-[calc(100%+6px)] z-50 w-80 bg-surface border border-white/[0.08] rounded-xl overflow-hidden"
            style={{ boxShadow: "0 12px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)" }}
          >
            <div className="px-3 py-2 border-b border-white/[0.06]">
              <div className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">Switch project</div>
              <p className="text-[10.5px] text-neutral-600 mt-0.5">
                Data scoped to the active project. Counts in real time.
              </p>
            </div>
            <div className="max-h-72 overflow-y-auto py-1">
              {projects.length === 0 && (
                <div className="px-3 py-4 text-center text-[12px] text-neutral-500">
                  No projects yet.
                </div>
              )}
              {projects.map((p) => {
                const isActive = p.project_id === active;
                return (
                  <button
                    key={p.project_id}
                    onClick={() => {
                      setActive(p.project_id);
                      setOpen(false);
                    }}
                    className={cn(
                      "w-full px-3 py-2.5 flex items-start gap-2.5 text-left transition-colors",
                      isActive ? "bg-emerald-500/[0.06]" : "hover:bg-white/[0.03]"
                    )}
                  >
                    <span
                      className={cn(
                        "w-4 h-4 rounded border flex items-center justify-center shrink-0 mt-0.5",
                        isActive ? "bg-emerald-500/30 border-emerald-400" : "border-white/[0.12]"
                      )}
                    >
                      {isActive && <Check className="w-2.5 h-2.5 text-emerald-300" strokeWidth={2.5} />}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12.5px] font-medium text-neutral-100 truncate">
                          {p.project_id}
                        </span>
                        {p.is_default && (
                          <span className="text-[9px] font-mono text-neutral-600 uppercase tracking-wider">
                            default
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-[10.5px] font-mono text-neutral-500">
                        <span>
                          <span className="text-neutral-400 tabular-nums">{p.requirement_count}</span> req
                        </span>
                        <span>
                          <span className="text-neutral-400 tabular-nums">{p.test_count}</span> test
                        </span>
                        <span className="ml-auto">
                          <span
                            className={cn(
                              "tabular-nums",
                              p.coverage_pct >= 80
                                ? "text-emerald-400"
                                : p.coverage_pct >= 40
                                  ? "text-amber-400"
                                  : "text-rose-400"
                            )}
                          >
                            {p.coverage_pct.toFixed(1)}%
                          </span>{" "}
                          cov
                        </span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
