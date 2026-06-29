"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/shared/PageHeader";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { Folder, Plus, Trash2, RefreshCw } from "lucide-react";

interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export default function ProjectPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    api.get<{ projects?: Project[] }>("/api/projects")
      .then(d => setProjects(d?.projects ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const createProject = async () => {
    if (!newName.trim()) return;
    try {
      const data = await api.post<{ id: string }>("/api/projects", { name: newName.trim() });
      setProjects(prev => [...prev, { id: data.id, name: newName.trim(), description: "", created_at: new Date().toISOString() }]);
      setNewName("");
    } catch {}
  };

  return (
    <div className="space-y-6">
      <PageHeader description="Manage project configurations and isolation" />

      <div className="flex items-center gap-3">
        <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="New project name..."
          className="flex-1 max-w-sm px-3 py-2 rounded-xl bg-card border border-white/[0.06] text-[13px] text-zinc-300 placeholder:text-zinc-600 outline-none focus:border-emerald-500/30"
          onKeyDown={e => { if (e.key === "Enter") createProject(); }} />
        <button onClick={createProject} disabled={!newName.trim()}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[12px] font-semibold bg-emerald-500 text-zinc-950 hover:bg-emerald-400 disabled:opacity-30 transition-all active:scale-[0.98]">
          <Plus className="w-3.5 h-3.5" strokeWidth={2} /> Create
        </button>
      </div>

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-16 rounded-xl shimmer-bg" />)}</div>
      ) : projects.length === 0 ? (
        <div className="text-center py-16 text-sm text-zinc-600">
          <Folder className="w-8 h-8 mx-auto mb-3 text-zinc-700" strokeWidth={1} />
          No projects yet. Create one to get started.
        </div>
      ) : (
        <div className="space-y-1.5">
          {projects.map((p, i) => (
            <motion.div key={p.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
              className="flex items-center gap-4 px-4 py-3 rounded-xl bg-card border border-white/[0.06] hover:border-white/[0.1] transition-all">
              <Folder className="w-4 h-4 text-zinc-500 shrink-0" strokeWidth={1.5} />
              <div className="flex-1 min-w-0">
                <span className="text-[13px] text-zinc-200 truncate block">{p.name}</span>
                <span className="text-[10px] text-zinc-600">{new Date(p.created_at).toLocaleDateString()}</span>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
