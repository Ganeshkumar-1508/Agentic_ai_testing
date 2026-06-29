"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";

export interface DashboardStats {
  totalTests: number;
  passed: number;
  failed: number;
  pending: number;
  passRate: number;
  byType: Array<{ type: string; count: number; passed: number }>;
}

export interface RecentTestRun {
  id: string;
  testName: string;
  status: string;
  duration: number;
  executedAt: string;
}

export interface DashboardData {
  stats: DashboardStats;
  recentTestRuns: RecentTestRun[];
  activeAgents: number;
}

async function fetchDashboard(): Promise<DashboardData> {
  const [statsData, runsData] = await Promise.all([
    api.get<any>("/api/dashboard/stats").then((d) => d?.stats),
    api.get<any>("/api/runs", { limit: "50", offset: "0" }).then((d) => d?.runs ?? []),
  ]);

  return {
    stats: {
      totalTests: Number(statsData?.totalTests ?? 0),
      passed: Number(statsData?.passed ?? 0),
      failed: Number(statsData?.failed ?? 0),
      pending: Number(statsData?.pending ?? 0),
      passRate: Number(statsData?.passRate ?? 0),
      byType: (statsData?.byType ?? []).map((t: any) => ({
        type: String(t.type ?? "unknown"),
        count: Number(t.count ?? 0),
        passed: Number(t.passed ?? 0),
      })),
    },
    recentTestRuns: runsData.slice(0, 10).map((r: any) => ({
      id: String(r.id),
      testName: r.id?.slice(0, 8) ?? "Unnamed Run",
      status: String(r.status ?? "unknown"),
      duration: Number(r.duration ?? 0),
      executedAt: String(r.createdAt ?? new Date().toISOString()),
    })),
    activeAgents: Number(statsData?.activeAgents ?? 0),
  };
}

export function useDashboard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
    staleTime: 30_000,
    retry: 2,
  });

  return {
    stats: data?.stats ?? null,
    recentTestRuns: data?.recentTestRuns ?? [],
    isLoading,
    error: error instanceof Error ? error.message : (error ? String(error) : null),
    refetch,
  };
}
