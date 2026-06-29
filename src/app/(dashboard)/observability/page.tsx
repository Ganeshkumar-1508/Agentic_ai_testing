"use client";

import { Suspense } from "react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ObservabilityStatus } from "@/components/observability/ObservabilityStatus";
import { CompactionSection } from "@/components/observability/CompactionSection";
import { ProviderEventsSection } from "@/components/observability/ProviderEventsSection";

function ObservabilityContent() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Observability"
        description="OpenTelemetry spans, context compaction, provider events, and 1M-context support."
      />
      <CompactionSection />
      <ObservabilityStatus />
      <ProviderEventsSection />
    </div>
  );
}

export default function ObservabilityPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[100dvh] flex items-center justify-center bg-background">
          <div className="text-sm text-zinc-600">Loading…</div>
        </div>
      }
    >
      <ObservabilityContent />
    </Suspense>
  );
}
