"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Trash2, Download, Clock, Shield, Check, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { toast } from "sonner";

export function DataPrivacySettings() {
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [retention, setRetention] = useState("30");

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await api.get("/api/sessions?limit=1000");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `testai-export-${new Date().toISOString().split("T")[0]}.json`;
      a.click(); URL.revokeObjectURL(url);
      toast.success("Data exported");
    } catch { toast.error("Export failed"); }
    setExporting(false);
  };

  const handleDelete = async () => {
    if (!confirmed) return;
    setDeleting(true);
    try {
      await api.post("/api/sessions/cleanup", { older_than_days: parseInt(retention) });
      toast.success(`Data older than ${retention} days deleted`);
      setConfirmed(false);
    } catch { toast.error("Delete failed"); }
    setDeleting(false);
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><Clock size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
          <div><h3 className="text-sm font-medium text-zinc-200">Data Retention</h3><p className="text-xs text-zinc-500">Automatically delete session data older than this many days</p></div>
        </div>
        <div className="flex items-center gap-3">
          <input type="number" value={retention} onChange={(e) => setRetention(e.target.value)} min="1" max="365" className="w-20 bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 font-mono text-center focus:outline-none focus:border-emerald-500/40" />
          <span className="text-sm text-zinc-400">days</span>
          <span className="text-[10px] text-zinc-600">Sessions older than this will be auto-deleted</span>
        </div>
      </div>

      <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><Download size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
          <div><h3 className="text-sm font-medium text-zinc-200">Export Data</h3><p className="text-xs text-zinc-500">Download all your session data as JSON</p></div>
        </div>
        <button onClick={handleExport} disabled={exporting} className="inline-flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors disabled:opacity-40 active:scale-[0.97]">
          <Download size={12} strokeWidth={1.5} />{exporting ? "Exporting..." : "Export My Data"}
        </button>
      </div>

      <div className="rounded-2xl border border-red-900/30 bg-red-900/10 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-red-900/30 flex items-center justify-center"><Trash2 size={16} className="text-red-400" strokeWidth={1.5} /></div>
          <div><h3 className="text-sm font-medium text-red-300">Delete Data</h3><p className="text-xs text-red-400/70">Permanently delete session data older than the retention period</p></div>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/20" />
            <span className="text-xs text-zinc-400">I understand this action cannot be undone</span>
          </label>
        </div>
        <button onClick={handleDelete} disabled={!confirmed || deleting} className="inline-flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-red-600/80 text-white hover:bg-red-600 disabled:opacity-40 transition-colors active:scale-[0.97]">
          <Trash2 size={12} strokeWidth={1.5} />{deleting ? "Deleting..." : `Delete Sessions Older Than ${retention} Days`}
        </button>
      </div>
    </div>
  );
}
