"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Download, Star, ExternalLink, Loader2, ChevronRight, Sparkles, Hash, AlertCircle, Globe } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface HubSkill {
  name: string;
  description: string;
  author: string;
  stars?: number;
  githubUrl?: string;
  forks?: number;
}

interface PaginationInfo {
  total: number;
  totalAll: number;
  page: number;
  limit: number;
  hasNext: boolean;
}

const CATEGORIES = ["All", "Document", "Design", "Engineering", "Communication", "Security", "DevOps", "Data"];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.03 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } },
};

export function SkillHubPanel() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [installing, setInstalling] = useState<string | null>(null);
  const [sort, setSort] = useState<"stars" | "name">("stars");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [skills, setSkills] = useState<HubSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState<PaginationInfo | null>(null);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ skills: HubSkill[]; pagination: PaginationInfo; fallback?: boolean }>(
        `/api/skills/hub?limit=24&sort=${sort}${search ? `&search=${encodeURIComponent(search)}` : ""}`
      );
      setSkills(data.skills || []);
      if (data.pagination) setPagination(data.pagination);
      if (data.fallback) toast.info("Live hub unavailable — showing curated skills");
    } catch {
      setSkills([]);
    }
    setLoading(false);
  }, [sort, search]);

  useEffect(() => { loadSkills(); }, [loadSkills]);

  const installSkill = async (skill: HubSkill) => {
    const url = skill.githubUrl?.replace("github.com", "raw.githubusercontent.com").replace("/tree/", "/") + "/SKILL.md";
    if (!url) { toast.error("No install URL"); return; }
    setInstalling(skill.name);
    try {
      await api.post("/api/skills/import", { url, name: skill.name });
      toast.success(`Installed ${skill.name}`);
    } catch {
      toast.error("Failed to install");
    }
    setInstalling(null);
  };

  const featured = useMemo(() => skills.filter((s) => (s.stars ?? 0) >= 50000).slice(0, 6), [skills]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 mb-1">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><Globe size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
        <div><h3 className="text-sm font-medium text-zinc-200">Skill Hub</h3>
          <p className="text-xs text-zinc-500">{pagination ? `${pagination.totalAll?.toLocaleString() || skills.length}+` : ""} skills from SkillsMP marketplace</p>
        </div>
      </div>

      {/* Featured skills */}
      {!search && featured.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-[10px] text-zinc-600 font-medium uppercase tracking-wider">
            <Sparkles size={11} strokeWidth={1.5} />
            Featured
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {featured.map((skill) => (
              <motion.button key={skill.name} layout
                onClick={() => setSearch(skill.name.split("-")[0])}
                className="shrink-0 flex items-center gap-2 px-3 py-2 rounded-xl bg-gradient-to-r from-emerald-500/8 to-emerald-500/3 border border-emerald-500/15 hover:border-emerald-500/30 transition-all active:scale-[0.98] group">
                <BookOpen size={12} className="text-emerald-400" strokeWidth={1.5} />
                <span className="text-[11px] text-zinc-300 font-medium whitespace-nowrap">{skill.name}</span>
                <span className="text-[9px] text-zinc-600 font-mono">{skill.author?.split("/")[0] || "?"}</span>
                <ChevronRight size={10} className="text-zinc-700 group-hover:text-zinc-500 transition-colors" strokeWidth={1.5} />
              </motion.button>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        {CATEGORIES.map((cat) => (
          <button key={cat} onClick={() => setCategory(cat)}
            className={cn("text-[10px] px-2.5 py-1 rounded-lg transition-all active:scale-[0.97]",
              category === cat ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-zinc-800/50 text-zinc-500 border border-zinc-700/30 hover:text-zinc-300")}>
            {cat}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <select value={sort} onChange={(e) => setSort(e.target.value as "stars" | "name")}
            className="text-[10px] bg-zinc-800/60 border border-zinc-700 rounded-lg px-2 py-1 text-zinc-500 outline-none focus:border-emerald-500/40">
            <option value="stars">Most stars</option>
            <option value="name">A-Z</option>
          </select>
          <input value={search} onChange={(e) => { setSearch(e.target.value); }} placeholder="Search 1.96M skills..."
            className="text-[11px] bg-zinc-800/60 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-zinc-300 placeholder-zinc-600 w-48 outline-none focus:border-emerald-500/40" />
        </div>
      </div>

      {/* Skill grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 rounded-xl border border-zinc-800/30 bg-zinc-900/20 shimmer" />
          ))}
        </div>
      ) : skills.length === 0 ? (
        <div className="flex flex-col items-center py-12 text-zinc-600 gap-2">
          <BookOpen size={20} strokeWidth={1} className="text-zinc-700" />
          <p className="text-sm">No skills found{search ? ` for "${search}"` : ""}</p>
          <p className="text-xs text-zinc-700">Try a different search term</p>
        </div>
      ) : (
        <>
          <motion.div variants={containerVariants} initial="hidden" animate="visible" className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {skills.map((skill, i) => {
              const isExpanded = expanded === skill.name;
              const isInstalling = installing === skill.name;
              return (
                <motion.div key={`${skill.name}-${i}`} variants={itemVariants} layout
                  className={cn("rounded-xl border bg-zinc-900/40 p-4 space-y-2 transition-all",
                    isExpanded ? "border-emerald-500/30" : "border-zinc-800/50 hover:border-zinc-700/50")}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                        skill.author === "anthropics" ? "bg-emerald-500/10" : "bg-zinc-800/50")}>
                        <BookOpen size={14} className={skill.author === "anthropics" ? "text-emerald-400" : "text-zinc-400"} strokeWidth={1.5} />
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-sm font-medium text-zinc-200 truncate">{skill.name}</h4>
                        <p className="text-[10px] text-zinc-600 font-mono truncate">{skill.author || "unknown"}</p>
                      </div>
                    </div>
                    <button onClick={() => installSkill(skill)} disabled={isInstalling}
                      className={cn("inline-flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-lg transition-all active:scale-[0.97] shrink-0",
                        isInstalling ? "bg-zinc-800 text-zinc-600" : "bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20")}>
                      {isInstalling ? <Loader2 size={10} className="animate-spin" /> : <Download size={10} strokeWidth={1.5} />}
                      {isInstalling ? "Installing..." : "Install"}
                    </button>
                  </div>

                  <p className="text-[11px] text-zinc-500 line-clamp-2">{skill.description}</p>

                  <div className="flex items-center gap-1.5">
                    {(skill.stars ?? 0) > 0 && (
                      <span className="text-[9px] text-zinc-600 flex items-center gap-0.5">
                        <Star size={9} className="text-zinc-600" strokeWidth={1.5} /> {skill.stars?.toLocaleString()}
                      </span>
                    )}
                    {skill.githubUrl && (
                      <button onClick={() => setExpanded(isExpanded ? null : skill.name)}
                        className="text-[9px] text-zinc-700 hover:text-zinc-500 transition-colors ml-auto">
                        {isExpanded ? "less" : "details"}
                      </button>
                    )}
                  </div>

                  <AnimatePresence>
                    {isExpanded && skill.githubUrl && (
                      <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="border-t border-zinc-800/20 pt-2 space-y-1.5 text-[10px]">
                        <a href={skill.githubUrl} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-zinc-500 hover:text-indigo-400 transition-colors">
                          <ExternalLink size={9} strokeWidth={1.5} /> View on GitHub
                        </a>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </motion.div>

          {pagination && pagination.totalAll && pagination.totalAll > skills.length && (
            <div className="text-center text-[10px] text-zinc-700">
              Showing {skills.length} of {pagination.totalAll.toLocaleString()} skills
            </div>
          )}
        </>
      )}

      <div className="text-[10px] text-zinc-700 text-center">
        Powered by <a href="https://skillsmp.com" target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">SkillsMP <ExternalLink size={9} strokeWidth={1.5} /></a> · {pagination?.totalAll?.toLocaleString() || "1.96M+"} agent skills indexed
      </div>
    </div>
  );
}
