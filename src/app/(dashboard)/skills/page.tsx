"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { BookOpen, Globe } from "lucide-react";
import { SkillsPanel } from "@/components/project/panels/SkillsPanel";
import { SkillHubPanel } from "@/components/skills/SkillHubPanel";
import { cn } from "@/lib/utils";

type Tab = "local" | "hub";

export default function SkillsPage() {
  const [tab, setTab] = useState<Tab>("local");

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
        <span className="text-xs font-mono text-zinc-600">/skills</span>
      </div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
            {tab === "hub" ? <Globe size={16} className="text-zinc-400" strokeWidth={1.5} /> : <BookOpen size={16} className="text-zinc-400" strokeWidth={1.5} />}
          </div>
          <div>
            <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Skills</h1>
            <p className="text-sm text-zinc-600 mt-1">Install, create, and manage reusable agent skills</p>
          </div>
        </div>
        <div className="flex gap-1 bg-zinc-900/50 border border-zinc-800/30 rounded-xl p-1">
          <button onClick={() => setTab("local")}
            className={cn("px-3 py-1.5 text-xs rounded-lg transition-colors", tab === "local" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300")}>
            Installed
          </button>
          <button onClick={() => setTab("hub")}
            className={cn("px-3 py-1.5 text-xs rounded-lg transition-colors", tab === "hub" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300")}>
            Hub
          </button>
        </div>
      </div>
      <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}>
        {tab === "local" ? <SkillsPanel /> : <SkillHubPanel />}
      </motion.div>
    </div>
  );
}
