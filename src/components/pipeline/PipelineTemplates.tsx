"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, Plus, Save, Trash2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface Template {
  id: string;
  name: string;
  description: string;
  requirements: string;
  mode: string;
  language: string;
  framework: string;
}

interface Props {
  onLoad: (requirements: string) => void;
  currentRequirements: string;
}

export function PipelineTemplates({ onLoad, currentRequirements }: Props) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showSave, setShowSave] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveDesc, setSaveDesc] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchTemplates = async () => {
    try {
      const data = await api.get<{ templates?: Template[] }>("/api/pipeline-templates");
      setTemplates(data?.templates ?? []);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  const handleSave = async () => {
    if (!saveName.trim() || !currentRequirements.trim()) return;
    setSaving(true);
    try {
      await api.post("/api/pipeline-templates", {
        name: saveName.trim(),
        description: saveDesc.trim(),
        requirements: currentRequirements,
        mode: "auto",
      });
      toast.success("Template saved");
      setSaveName("");
      setSaveDesc("");
      setShowSave(false);
      fetchTemplates();
    } catch {
      toast.error("Failed to save template");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/api/pipeline-templates/${id}`);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      toast.success("Template deleted");
    } catch {
      toast.error("Failed to delete template");
    }
  };

  return (
    <div className="border border-white/[0.05] rounded-[1.5rem] bg-surface overflow-hidden shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full px-4 py-3 text-xs text-neutral-400 hover:text-neutral-200 transition-colors duration-200"
      >
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-white/[0.03] flex items-center justify-center">
            <FileText size={12} strokeWidth={1.5} className="text-neutral-500" />
          </div>
          <span className="font-medium text-neutral-300">Templates</span>
          {templates.length > 0 && (
            <span className="text-[10px] text-neutral-600 font-mono tabular-nums">{templates.length}</span>
          )}
        </div>
        <motion.div
          animate={{ rotate: open ? 0 : -90 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
          <ChevronDown size={12} strokeWidth={1.5} className="text-neutral-500" />
        </motion.div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 space-y-2 border-t border-white/[0.05] pt-2">
              {currentRequirements.trim() && (
                <>
                  {showSave ? (
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-2 p-3 rounded-xl bg-white/[0.02] border border-white/[0.05]"
                    >
                      <div className="space-y-1.5">
                        <label className="text-[10px] text-neutral-500 font-medium uppercase tracking-wider">Name</label>
                        <input
                          value={saveName}
                          onChange={(e) => setSaveName(e.target.value)}
                          placeholder="e.g. API Regression Suite"
                          className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 outline-none focus:border-emerald-500/40 transition-colors"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-[10px] text-neutral-500 font-medium uppercase tracking-wider">Description</label>
                        <input
                          value={saveDesc}
                          onChange={(e) => setSaveDesc(e.target.value)}
                          placeholder="What does this template do?"
                          className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 outline-none focus:border-emerald-500/40 transition-colors"
                        />
                      </div>
                      <div className="flex gap-2 pt-1">
                        <button
                          onClick={handleSave}
                          disabled={saving || !saveName.trim()}
                          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500 text-black font-medium hover:bg-emerald-400 transition-all duration-200 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {saving ? <Loader2 size={11} className="animate-spin" strokeWidth={1.5} /> : <Save size={11} strokeWidth={1.5} />}
                          Save Template
                        </button>
                        <button
                          onClick={() => setShowSave(false)}
                          className="px-3 py-1.5 text-xs rounded-lg bg-white/[0.04] text-neutral-400 hover:text-neutral-200 transition-colors active:scale-[0.97]"
                        >
                          Cancel
                        </button>
                      </div>
                    </motion.div>
                  ) : (
                    <button
                      onClick={() => setShowSave(true)}
                      className="flex items-center gap-1.5 w-full px-2.5 py-2 text-xs text-neutral-400 hover:text-neutral-200 rounded-lg hover:bg-white/[0.03] transition-all duration-200 active:scale-[0.97]"
                    >
                      <div className="w-5 h-5 rounded-md bg-emerald-500/10 flex items-center justify-center">
                        <Plus size={10} strokeWidth={1.5} className="text-emerald-400" />
                      </div>
                      Save current as template
                    </button>
                  )}
                </>
              )}

              {loading ? (
                <div className="space-y-2 py-2">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-10 bg-white/[0.02] rounded-lg animate-pulse" />
                  ))}
                </div>
              ) : templates.length === 0 ? (
                <div className="flex flex-col items-center py-6 text-center">
                  <div className="w-8 h-8 rounded-xl bg-white/[0.02] border border-white/[0.05] flex items-center justify-center mb-2">
                    <FileText size={14} strokeWidth={1} className="text-neutral-600" />
                  </div>
                  <p className="text-xs text-neutral-500">No templates yet</p>
                  <p className="text-[10px] text-neutral-700 mt-0.5">Save a pipeline configuration to reuse it later</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {templates.map((t, i) => (
                    <motion.div
                      key={t.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.03, duration: 0.2 }}
                      className="flex items-center justify-between px-2.5 py-2 rounded-lg hover:bg-white/[0.03] transition-colors group"
                    >
                      <button
                        onClick={() => { onLoad(t.requirements); setOpen(false); toast.success(`Loaded "${t.name}"`); }}
                        className="flex-1 text-left min-w-0"
                      >
                        <p className="text-xs font-medium text-neutral-200 truncate">{t.name}</p>
                        {t.description && (
                          <p className="text-[10px] text-neutral-600 truncate mt-0.5">{t.description}</p>
                        )}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(t.id); }}
                        className="p-1 rounded-md text-neutral-600 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all active:scale-[0.97]"
                        title="Delete template"
                      >
                        <Trash2 size={11} strokeWidth={1.5} />
                      </button>
                    </motion.div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
