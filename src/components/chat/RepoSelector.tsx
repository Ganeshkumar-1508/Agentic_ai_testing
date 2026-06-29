"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { GitBranch, Globe, Lock, Search, X, AlertCircle, Plus } from "lucide-react";

export interface RepoInfo {
  id: string;
  full_name: string;
  is_public: boolean;
  main_branch: string;
  stargazers_count: number;
}

interface RepoSelectorProps {
  selectedRepo: RepoInfo | null;
  onSelect: (repo: RepoInfo | null) => void;
  selectedBranch: string;
  onBranchChange: (branch: string) => void;
}

export function RepoSelector({
  selectedRepo,
  onSelect,
  selectedBranch,
  onBranchChange,
}: RepoSelectorProps) {
  const [open, setOpen] = useState(false);
  const [repos, setRepos] = useState<RepoInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [branchOpen, setBranchOpen] = useState(false);
  const [branches, setBranches] = useState<string[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .get<{ repos?: RepoInfo[]; error?: string }>("/api/integrations/repos")
      .then((data) => {
        if (data?.error === "no_github_token") {
          setError("no_token");
          setRepos([]);
        } else {
          setRepos(data?.repos ?? []);
          setError(null);
        }
      })
      .catch(() => setError("load_failed"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = search.trim()
    ? repos.filter((r) =>
        r.full_name.toLowerCase().includes(search.toLowerCase()),
      )
    : repos;

  const handleSelect = useCallback(
    (repo: RepoInfo) => {
      onSelect(repo);
      onBranchChange(repo.main_branch);
      setOpen(false);
      setSearch("");
      setBranches([]);
    },
    [onSelect, onBranchChange],
  );

  const handleRemove = useCallback(() => {
    onSelect(null);
    onBranchChange("main");
  }, [onSelect, onBranchChange]);

  const handleBranchPicker = useCallback(async () => {
    if (!selectedRepo) return;
    setBranchOpen((v) => !v);
    if (branches.length === 0) {
      try {
        const data = await api.get<{ branches?: { name: string }[] }>(
          `/api/integrations/repos/${encodeURIComponent(selectedRepo.full_name)}/branches`,
        );
        setBranches(data?.branches?.map((b) => b.name) ?? [selectedRepo.main_branch]);
      } catch {
        setBranches([selectedRepo.main_branch]);
      }
    }
  }, [selectedRepo, branches.length]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setBranchOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  if (error === "no_token") {
    return (
      <div className="flex items-center gap-2 px-1 py-1.5">
        <a
          href="/settings"
          className="inline-flex items-center gap-1.5 px-3 h-7 rounded-lg bg-emerald-500/10 text-emerald-400 text-[11px] font-semibold hover:bg-emerald-500/20 transition-colors active:scale-[0.97]"
        >
          <Plus className="w-3 h-3" strokeWidth={2} />
          Connect GitHub
        </a>
        <span className="text-[10px] text-zinc-600">
          Add a token in Settings to select repos
        </span>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative px-1 pt-1.5 pb-0.5">
      {selectedRepo ? (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-lg bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.08] hover:border-white/[0.1] transition-all active:scale-[0.97] group"
          >
            {selectedRepo.is_public ? (
              <Globe className="w-3 h-3 text-zinc-500" strokeWidth={1.5} />
            ) : (
              <Lock className="w-3 h-3 text-zinc-500" strokeWidth={1.5} />
            )}
            <span className="text-[11px] font-medium text-zinc-300 group-hover:text-zinc-200 transition-colors">
              {selectedRepo.full_name}
            </span>
          </button>

          <div className="relative">
            <button
              onClick={handleBranchPicker}
              className="inline-flex items-center gap-1 px-2 h-7 rounded-lg bg-white/[0.02] border border-white/[0.06] hover:bg-white/[0.06] transition-all active:scale-[0.97] text-[11px] text-zinc-500"
            >
              <GitBranch className="w-3 h-3" strokeWidth={1.5} />
              {selectedBranch}
            </button>
            <AnimatePresence>
              {branchOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -4, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -4, scale: 0.96 }}
                  transition={{ type: "spring", stiffness: 200, damping: 22 }}
                  className="absolute left-0 top-full mt-1 w-44 max-h-48 overflow-y-auto rounded-xl bg-zinc-900 border border-white/[0.08] shadow-[0_8px_32px_-8px_rgba(0,0,0,0.4)] z-50 py-1"
                >
                  {branches.map((b) => (
                    <button
                      key={b}
                      onClick={() => {
                        onBranchChange(b);
                        setBranchOpen(false);
                      }}
                      className={cn(
                        "w-full text-left px-3 py-1.5 text-[11px] transition-colors",
                        b === selectedBranch
                          ? "text-emerald-400 bg-emerald-500/10"
                          : "text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04]",
                      )}
                    >
                      {b}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <button
            onClick={handleRemove}
            className="p-1 rounded-md hover:bg-white/[0.05] text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            <X className="w-3 h-3" strokeWidth={1.5} />
          </button>
        </div>
      ) : (
        <button
          onClick={() => setOpen(true)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-lg bg-white/[0.03] border border-dashed border-white/[0.08] hover:bg-white/[0.06] hover:border-white/[0.12] transition-all active:scale-[0.97] text-[11px] text-zinc-500"
        >
          <GitBranch className="w-3 h-3" strokeWidth={1.5} />
          {loading ? "Loading repos…" : "Select repository"}
        </button>
      )}

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 200, damping: 22 }}
            className="absolute left-1 top-full mt-1 w-80 max-h-72 overflow-hidden rounded-xl bg-zinc-900 border border-white/[0.08] shadow-[0_12px_40px_-12px_rgba(0,0,0,0.5)] z-50"
          >
            <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.06]">
              <Search className="w-3.5 h-3.5 text-zinc-500 shrink-0" strokeWidth={1.5} />
              <input
                ref={inputRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search repos…"
                className="flex-1 bg-transparent text-xs text-zinc-300 placeholder:text-zinc-600 outline-none"
              />
            </div>
            <div className="overflow-y-auto max-h-56 py-1">
              {filtered.length === 0 ? (
                <div className="px-3 py-4 text-center text-[11px] text-zinc-600">
                  {search ? "No matching repos" : "No repos connected"}
                </div>
              ) : (
                filtered.map((repo, i) => (
                  <motion.button
                    key={repo.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.02, duration: 0.15 }}
                    onClick={() => handleSelect(repo)}
                    className={cn(
                      "w-full text-left px-3 py-2 transition-colors",
                      selectedRepo?.id === repo.id
                        ? "bg-emerald-500/10"
                        : "hover:bg-white/[0.04]",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      {repo.is_public ? (
                        <Globe className="w-3 h-3 text-zinc-600 shrink-0" strokeWidth={1.5} />
                      ) : (
                        <Lock className="w-3 h-3 text-zinc-600 shrink-0" strokeWidth={1.5} />
                      )}
                      <span className="text-xs text-zinc-300 truncate flex-1">
                        {repo.full_name}
                      </span>
                      <span className="text-[10px] text-zinc-600 shrink-0">
                        {repo.main_branch}
                      </span>
                    </div>
                  </motion.button>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
