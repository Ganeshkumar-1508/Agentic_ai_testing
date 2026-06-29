"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";
import { DigestHero } from "@/components/dashboard/DigestHero";
import { DigestMetricRow } from "@/components/dashboard/DigestMetricRow";
import { DigestTimeline } from "@/components/dashboard/DigestTimeline";
import { DigestFailures } from "@/components/dashboard/DigestFailures";
import { DigestInsights } from "@/components/dashboard/DigestInsights";
import { DigestCostBar } from "@/components/dashboard/DigestCostBar";
import { DigestChannels } from "@/components/dashboard/DigestChannels";
import { DigestAttention } from "@/components/dashboard/DigestAttention";

export function DigestTab({ overview, isLoading }: { overview: any; isLoading: boolean }) {
  const { data: dailyData } = useQuery({
    queryKey: ["daily-stats"],
    queryFn: () => api.get<any>("/api/dashboard/daily-stats?days=30"),
    staleTime: 60_000,
  });
  const { data: activityData } = useQuery({
    queryKey: ["pipeline-activity"],
    queryFn: () => api.get<any>("/api/pipeline-activity/recent", { limit: "14" }),
    staleTime: 30_000,
  });
  const { data: costData } = useQuery({
    queryKey: ["cost-daily-trend"],
    queryFn: () => api.get<any>("/api/cost/daily-trend"),
    staleTime: 60_000,
  });
  const { data: digestConfigs } = useQuery({
    queryKey: ["digest-configs"],
    queryFn: () => api.get<any>("/api/digest/configs"),
    staleTime: 120_000,
  });

  const days = dailyData?.days ?? [];
  const yesterday = days.length >= 2 ? days[days.length - 2] : null;
  const sessions = activityData?.sessions ?? [];
  const trend = costData?.days ?? [];
  const configs = digestConfigs?.configs ?? [];
  const failures = ((overview?.recent_failures ?? []) as Array<{ name?: string; test_name?: string; count?: number }>).map((f) => ({ test_name: f.test_name || f.name || "unknown", error: undefined, created_at: undefined }));

  return (
    <div className="space-y-6">
      <DigestHero overview={overview} loading={isLoading} yesterday={yesterday} digestConfigs={configs} />
      <DigestMetricRow overview={overview} loading={isLoading} sessions={sessions} />
      <DigestTimeline sessions={sessions} />
      <DigestFailures failures={failures} loading={isLoading} />
      <DigestInsights overview={overview} loading={isLoading} />
      <DigestCostBar trend={trend} />
      <DigestChannels configs={configs} />
      <DigestAttention overview={overview} loading={isLoading} />
    </div>
  );
}
