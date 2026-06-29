"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X, Search, Trash2, Puzzle, BookOpen, Check, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { toast } from "sonner";

interface Skill {
  name: string;
  description: string;
  version: string;
  author: string;
  license: string;
  platforms: string[] | string;
  tags: string[];
  category: string;
  path: string;
  requires_toolsets: string[];
}

const SPRING = { type: "spring" as const, stiffness: 100, damping: 20 };

function platformString(p: Skill["platforms"]): string {
  if (Array.isArray(p)) return p.join(", ");
  if (typeof p === "string" && p.length) return p;
  return "any";
}

export function SkillsPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", content: "" });
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: skillsResp, isLoading } = useQuery<{ skills: Skill[]; total: number }>({
    queryKey: ["skills"],
    queryFn: () => api.get("/api/skills?limit=200"),
    staleTime: 60_000,
  });

  const skills = skillsResp?.skills ?? [];
  const total = skillsResp?.total ?? skills.length;

  const categories = useMemo(() => {
    const set = new Set<string>();
    skills.forEach((s) => { if (s.category) set.add(s.category); });
    return Array.from(set).sort();
  }, [skills]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return skills.filter((s) => {
      if (category !== "all" && s.category !== category) return false;
      if (q && !(s.name ?? "").toLowerCase().includes(q) && !(s.description ?? "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [skills, search, category]);

  const createMut = useMutation({
    mutationFn: async () => {
      await api.post(`/api/skills/${encodeURIComponent(form.name)}`, { content: form.content });
    },
    onSuccess: () => {
      toast.success("Skill created");
      setShowForm(false);
      setForm({ name: "", content: "" });
      queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
    onError: (e: Error) => toast.error(e.message ?? "Failed to create skill"),
  });

  const deleteMut = useMutation({
    mutationFn: async (name: string) => { await api.delete(`/api/skills/${encodeURIComponent(name)}`); },
    onSuccess: () => { toast.success("Skill deleted"); queryClient.invalidateQueries({ queryKey: ["skills"] }); },
    onError: (e: Error) => toast.error(e.message ?? "Failed to delete"),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight text-zinc-100">Agent Skills</h2>
          <p className="text-sm text-zinc-500 mt-1">Reusable instruction packs an agent can load on demand. Bundled skills come from the repo; user skills are yours to edit.</p>
        </div>
        <motion.button whileTap={{ scale: 0.97 }} onClick={() => setShowForm(!showForm)}
          className="h-9 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 text-xs font-semibold transition-colors flex items-center gap-1.5 shrink-0">
          {showForm ? <X className="w-3.5 h-3.5" strokeWidth={2} /> : <Plus className="w-3.5 h-3.5" strokeWidth={2} />}
          {showForm ? "Cancel" : "New Skill"}
        </motion.button>
      </div>

      {/* Strip — no boxed cards (anti-card-overuse) */}
      <div className="flex items-stretch border-y border-white/[0.06] divide-x divide-white/[0.06]">
        {[
          { label: "Total", value: total },
          { label: "Visible", value: filtered.length },
          { label: "Categories", value: categories.length },
        ].map((s) => (
          <div key={s.label} className="flex-1 px-6 py-4 flex items-baseline gap-3">
            <span className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.14em]">{s.label}</span>
            <motion.span key={s.value} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}
              className="text-2xl font-mono tabular-nums tracking-tight text-zinc-100">{s.value}</motion.span>
          </div>
        ))}
      </div>

      {/* Create form */}
      <AnimatePresence>
        {showForm && (
          <motion.section initial={{ opacity: 0, y: -8, height: 0 }} animate={{ opacity: 1, y: 0, height: "auto" }} exit={{ opacity: 0, y: -8, height: 0 }} transition={SPRING}
            className="overflow-hidden">
            <div className="bg-white/[0.015] border border-white/[0.06] rounded-3xl p-6 space-y-4">
              <div>
                <h3 className="text-sm font-medium text-zinc-200">Create a skill</h3>
                <p className="text-[11px] text-zinc-600 mt-0.5">SKILL.md content with YAML frontmatter.</p>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_auto] gap-3">
                <div>
                  <label className="text-[10px] font-mono text-zinc-600 block mb-1.5">Name</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="my-custom-skill"
                    className="w-full h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors font-mono" />
                </div>
                <div>
                  <label className="text-[10px] font-mono text-zinc-600 block mb-1.5">SKILL.md</label>
                  <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })}
                    rows={8}
                    placeholder={"---\nname: my-skill\ndescription: What this skill does.\nversion: 1.0.0\n---\n\nInstructions for the agent..."}
                    className="w-full h-40 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 py-2.5 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors resize-none font-mono leading-relaxed" />
                </div>
                <div className="flex items-end">
                  <motion.button whileTap={{ scale: 0.97 }} onClick={() => createMut.mutate()} disabled={!form.name || !form.content || createMut.isPending}
                    className="h-10 px-5 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-950 text-xs font-semibold transition-colors flex items-center gap-1.5">
                    {createMut.isPending ? <span className="w-3.5 h-3.5 border-2 border-zinc-950 border-t-transparent rounded-full animate-spin" /> : <Check className="w-3.5 h-3.5" strokeWidth={2} />}
                    {createMut.isPending ? "Saving" : "Save"}
                  </motion.button>
                </div>
              </div>
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      {/* Filters — slim, not boxed */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" strokeWidth={1.5} />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search skills by name or description…"
            className="w-full h-9 pl-10 pr-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-white/[0.12] transition-colors" />
        </div>
        <div className="flex bg-white/[0.02] border border-white/[0.06] rounded-xl p-0.5 gap-0.5">
          {["all", ...categories].slice(0, 6).map((c) => (
            <button key={c} onClick={() => setCategory(c)}
              className={cn("px-2.5 h-8 rounded-lg text-[10.5px] font-medium transition-colors",
                category === c ? "bg-white/[0.06] text-zinc-100" : "text-zinc-600 hover:text-zinc-300")}>
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Skills list */}
      <section>
        {isLoading ? (
          <div className="space-y-px">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-16 border-b border-white/[0.04] flex items-center gap-4 px-4">
                <div className="w-8 h-8 rounded-lg shimmer-bg" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-40 rounded shimmer-bg" />
                  <div className="h-2.5 w-64 rounded shimmer-bg" />
                </div>
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}
            className="py-20 text-center">
            <motion.div animate={{ y: [0, -3, 0] }} transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
              className="w-12 h-12 mx-auto rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-4">
              <Puzzle className="w-5 h-5 text-zinc-600" strokeWidth={1.2} />
            </motion.div>
            <h3 className="text-sm font-medium text-zinc-200">{search || category !== "all" ? "No skills match" : "No skills yet"}</h3>
            <p className="text-xs text-zinc-600 mt-1.5 max-w-xs mx-auto">
              {search || category !== "all" ? "Try clearing the search or filter." : "Click \"New Skill\" to author your first one."}
            </p>
          </motion.div>
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {filtered.slice(0, 200).map((s, i) => {
              const isOpen = expanded === s.name;
              const cats = s.path?.split("/").filter(Boolean).slice(0, 2).join(" / ") ?? "";
              return (
                <motion.div key={s.name} layout="position" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ ...SPRING, delay: Math.min(i * 0.015, 0.3) }}>
                  <button onClick={() => setExpanded(isOpen ? null : s.name)}
                    className={cn("w-full group grid grid-cols-[40px_1fr_120px_120px_100px] gap-4 items-center text-left px-4 py-3.5 transition-colors",
                      isOpen ? "bg-white/[0.025]" : "hover:bg-white/[0.02]")}>
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/15 flex items-center justify-center">
                      <Puzzle className="w-3.5 h-3.5 text-emerald-300" strokeWidth={1.5} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-[13px] text-zinc-100 truncate font-medium">{s.name}</div>
                      <div className="text-[11px] text-zinc-500 mt-0.5 truncate">{s.description || "—"}</div>
                    </div>
                    <div className="text-[10.5px] font-mono text-zinc-500 truncate" title={s.author}>{s.author || "—"}</div>
                    <div className="text-[10px] font-mono text-zinc-600 truncate" title={cats}>{cats || "—"}</div>
                    <div className="flex items-center justify-end gap-1.5">
                      <span className="text-[10px] font-mono text-zinc-600">v{s.version || "1"}</span>
                      <motion.span animate={{ rotate: isOpen ? 90 : 0 }} transition={SPRING} className="text-zinc-600">
                        <ChevronRight className="w-3 h-3" strokeWidth={2} />
                      </motion.span>
                    </div>
                  </button>
                  <AnimatePresence>
                    {isOpen && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={SPRING}
                        className="overflow-hidden bg-white/[0.02]">
                        <div className="px-4 py-4 pl-[68px] grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2 text-[11px]">
                          <Row label="License" value={s.license || "—"} />
                          <Row label="Platforms" value={platformString(s.platforms)} />
                          <Row label="Path" value={s.path} mono />
                          <Row label="Category" value={s.category} />
                          {s.requires_toolsets?.length > 0 && (
                            <div className="md:col-span-2 pt-2">
                              <div className="text-[10px] font-mono text-zinc-600 mb-1.5">Requires toolsets</div>
                              <div className="flex flex-wrap gap-1.5">
                                {s.requires_toolsets.map((t) => (
                                  <span key={t} className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.06]">{t}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          <div className="md:col-span-2 pt-3 mt-1 border-t border-white/[0.04] flex justify-end">
                            <motion.button whileTap={{ scale: 0.95 }} onClick={(e) => { e.stopPropagation(); deleteMut.mutate(s.name); }}
                              disabled={deleteMut.isPending}
                              className="h-7 px-3 rounded-lg text-[10.5px] font-medium text-zinc-500 hover:text-rose-300 hover:bg-rose-500/10 transition-colors flex items-center gap-1.5 disabled:opacity-40">
                              <Trash2 className="w-3 h-3" strokeWidth={1.5} /> Delete skill
                            </motion.button>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
            {filtered.length > 200 && (
              <div className="text-center text-[10px] text-zinc-600 py-3 font-mono">Showing first 200 of {filtered.length}. Refine the search to see more.</div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="text-[10px] font-mono text-zinc-600 w-20 shrink-0">{label}</span>
      <span className={cn("text-zinc-300 truncate", mono && "font-mono text-[10.5px]")} title={value}>{value}</span>
    </div>
  );
}
