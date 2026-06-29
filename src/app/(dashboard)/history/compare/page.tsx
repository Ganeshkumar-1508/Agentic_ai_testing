"use client";

import { Suspense } from "react";
import { GitCompare } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";

function CompareContent() {
  return (
    <div className="space-y-6">
      <PageHeader description="Compare two pipeline runs side by side" />
      <div className="text-center py-16 text-sm text-zinc-600">
        <GitCompare className="w-8 h-8 mx-auto mb-3 text-zinc-700" strokeWidth={1} />
        <p>Select two runs from the Run Analysis page to compare them.</p>
        <a href="/compare" className="text-emerald-400 hover:text-emerald-300 mt-2 inline-block">Go to Run Analysis</a>
      </div>
    </div>
  );
}

export default function HistoryComparePage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] flex items-center justify-center bg-background"><div className="flex items-center gap-3 text-zinc-600"><GitCompare className="w-4 h-4 animate-spin" strokeWidth={1.5} /><span className="text-sm">Loading...</span></div></div>}>
      <CompareContent />
    </Suspense>
  );
}
