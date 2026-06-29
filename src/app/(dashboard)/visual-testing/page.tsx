"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/shared/PageHeader";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { Eye, Image, Clock } from "lucide-react";

interface VisualBaseline {
  id: string;
  test_name: string;
  url: string;
  image_hash: string;
  viewport: string;
  created_at: string;
}

export default function VisualTestingPage() {
  const [baselines, setBaselines] = useState<VisualBaseline[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ baselines?: VisualBaseline[] }>("/api/testing/visual/baselines")
      .then(d => setBaselines(d?.baselines ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const uniqueTests = new Set(baselines.map(b => b.test_name)).size;
  const uniqueViewports = new Set(baselines.map(b => b.viewport)).size;

  return (
    <div className="space-y-6">
      <PageHeader title="Visual Testing" description="Visual regression testing with screenshot comparison" />

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Baselines", value: baselines.length, icon: Eye, color: "text-zinc-300" },
          { label: "Unique Tests", value: uniqueTests, icon: Image, color: "text-emerald-400" },
          { label: "Viewports", value: uniqueViewports, icon: Eye, color: "text-blue-400" },
          { label: "Latest", value: baselines.length > 0 ? new Date(baselines[0].created_at).toLocaleDateString() : "None", icon: Clock, color: "text-zinc-500" },
        ].map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
            className="rounded-[2rem] p-4 card-wireframe">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">{s.label}</span>
              <s.icon className={`w-3.5 h-3.5 ${s.color}`} strokeWidth={1.5} />
            </div>
            <div className={`text-2xl font-semibold font-mono ${s.color}`}>{s.value}</div>
          </motion.div>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-16 rounded-xl shimmer-bg" />)}</div>
      ) : baselines.length === 0 ? (
        <div className="text-center py-16 text-sm text-zinc-600">
          <Eye className="w-8 h-8 mx-auto mb-3 text-zinc-700" strokeWidth={1} />
          No visual baselines captured yet
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {baselines.map((b, i) => (
            <motion.div key={b.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
              className="rounded-[2rem] p-5 card-wireframe">
              <div className="flex items-center justify-between mb-3">
                <span className="text-[13px] text-zinc-200 font-medium truncate">{b.test_name}</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500 font-mono">{b.viewport}</span>
              </div>
              <div className="flex gap-3 text-[11px] font-mono text-zinc-500">
                <span className="truncate">{b.url}</span>
                <span>{new Date(b.created_at).toLocaleDateString()}</span>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
