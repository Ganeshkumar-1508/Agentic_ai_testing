"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { CronPanel } from "@/components/project/panels/CronPanel";
import { BlueprintPanel } from "@/components/cron/BlueprintPanel";
import { PageHeader } from "@/components/shared/PageHeader";

type Tab = "jobs" | "blueprints";

export default function CronPage() {
  const [tab, setTab] = useState<Tab>("jobs");

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <PageHeader label="Scheduled Jobs" description="Recurring pipelines and automated workflows" />
      <div className="flex gap-1 mb-6 bg-zinc-900/50 border border-zinc-800/30 rounded-xl p-1 w-fit">
        <button onClick={() => setTab("jobs")}
          className={`px-4 py-1.5 text-xs rounded-lg transition-colors ${tab === "jobs" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}>
          Cron Jobs
        </button>
        <button onClick={() => setTab("blueprints")}
          className={`px-4 py-1.5 text-xs rounded-lg transition-colors ${tab === "blueprints" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}>
          Blueprints
        </button>
      </div>
      <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}>
        {tab === "jobs" ? <CronPanel /> : <BlueprintPanel />}
      </motion.div>
    </div>
  );
}
