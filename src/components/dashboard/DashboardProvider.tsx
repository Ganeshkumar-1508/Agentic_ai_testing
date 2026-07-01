"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";
import type { SystemHealthData } from "@/components/dashboard/SystemHealthBar";
import type { SprintTrendsData } from "@/components/dashboard/SprintTrends";

interface DashboardData {
  tests_24h?: { total: number; passed: number; failed: number; skipped: number };
  pass_rate_24h?: number;
  pipeline_runs_24h?: number;
  flaky_tests?: number;
  active_agents?: number;
  quarantined_tests?: number;
  prs_needing_attention?: number;
  recent_failures?: Array<{ name: string; count: number }>;
  quality_score?: number;
  quality_components?: Record<string, { label: string; raw: number; weighted: number; weight: number }>;
  timestamp?: string;
  [key: string]: unknown;
}

interface AnalyticsData {
  spark_tests?: number[];
  spark_pass_rate?: number[];
  spark_flaky?: number[];
  change_tests_pct?: number;
  change_pass_pct?: number;
  change_flaky_pct?: number;
  [key: string]: unknown;
}

interface CoverageGapData {
  total: number;
  withGaps: number;
  noTests: number;
}

interface CoverageData {
  line_pct: number;
  branch_pct: number;
  sparkline: Array<{ date: string; line_pct: number }>;
  change_pct: number;
  untested_requirements: number;
  last_updated: string | null;
  days: number;
}

interface RcaCategory {
  count: number;
  pct: number;
  topTests: string[];
}

interface FailureCategoriesData {
  defects: RcaCategory;
  flakes: RcaCategory;
  environment: RcaCategory;
  unknown: RcaCategory;
  total: number;
}

interface DashboardContextValue {
  overview: DashboardData | undefined;
  analytics: AnalyticsData | undefined;
  coverageGaps: CoverageGapData | undefined;
  coverage: CoverageData | undefined;
  failureCategories: FailureCategoriesData | undefined;
  systemHealth: SystemHealthData | undefined;
  sprintTrends: SprintTrendsData | undefined;
  isLoading: boolean;
  isInitialLoading: boolean;
  isOverviewLoading: boolean;
  isAnalyticsLoading: boolean;
  isCoverageLoading: boolean;
  isFailureCategoriesLoading: boolean;
  isSystemHealthLoading: boolean;
  isSprintTrendsLoading: boolean;
  error: Error | null;
}

const DashboardContext = createContext<DashboardContextValue>({
  overview: undefined,
  analytics: undefined,
  coverageGaps: undefined,
  coverage: undefined,
  failureCategories: undefined,
  systemHealth: undefined,
  sprintTrends: undefined,
  isLoading: true,
  isInitialLoading: true,
  isOverviewLoading: true,
  isAnalyticsLoading: true,
  isCoverageLoading: true,
  isFailureCategoriesLoading: true,
  isSystemHealthLoading: true,
  isSprintTrendsLoading: true,
  error: null,
});

export function useDashboard() {
  return useContext(DashboardContext);
}

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { data: overview, isLoading: overviewLoading, error: overviewError } = useQuery<DashboardData>({
    queryKey: ["dashboard-overview"],
    queryFn: () => api.get("/api/dashboard/overview"),
    refetchInterval: 30_000,
    retry: 2,
  });

  const { data: analytics, isLoading: analyticsLoading, error: analyticsError } = useQuery<AnalyticsData>({
    queryKey: ["analytics-30d"],
    queryFn: () => api.get("/api/dashboard/widgets/analytics-30d"),
    refetchInterval: 60_000,
    retry: 2,
  });

  const { data: coverageData, isLoading: coverageLoading, error: coverageError } = useQuery<{ gaps?: Array<{ has_gap: boolean; gap_type: string }> }>({
    queryKey: ["coverage-gaps-kpi"],
    queryFn: async () => {
      const data = await api.get<{ gaps?: Array<{ has_gap: boolean; gap_type: string }> }>("/api/traceability/coverage-gaps");
      return data;
    },
    refetchInterval: 60_000,
    retry: 2,
  });

  const { data: coverage, isLoading: coverageWidgetLoading, error: coverageWidgetError } = useQuery<CoverageData>({
    queryKey: ["coverage-widget"],
    queryFn: () => api.get<CoverageData>("/api/dashboard/widgets/coverage?days=30"),
    refetchInterval: 60_000,
    retry: 2,
  });

  const { data: rcaData, isLoading: rcaLoading, error: rcaError } = useQuery<{
    total_failures: number;
    defect_count: number;
    flake_count: number;
    env_count: number;
    unknown_count: number;
    top_defects: Array<{ tests?: string[] }>;
    top_flakes: Array<{ tests?: string[] }>;
    top_env: Array<{ tests?: string[] }>;
    top_unknown: Array<{ tests?: string[] }>;
  }>({
    queryKey: ["dashboard-rca-clusters"],
    queryFn: () => api.get("/api/dashboard/widgets/rca-clusters?days=30"),
    refetchInterval: 60_000,
    retry: 2,
  });

  const { data: systemHealth, isLoading: systemHealthLoading, error: systemHealthError } = useQuery<SystemHealthData>({
    queryKey: ["dashboard-system-health"],
    queryFn: () => api.get<SystemHealthData>("/api/dashboard/widgets/system-health"),
    refetchInterval: 30_000,
    retry: 1,
  });

  const { data: sprintTrends, isLoading: sprintTrendsLoading, error: sprintTrendsError } = useQuery<SprintTrendsData>({
    queryKey: ["dashboard-sprint-trends"],
    queryFn: () => api.get<SprintTrendsData>("/api/dashboard/widgets/sprint-trends?sprints=5"),
    refetchInterval: 120_000,
    retry: 1,
  });

  const firstError = overviewError ?? analyticsError ?? coverageError ?? coverageWidgetError ?? rcaError ?? systemHealthError ?? sprintTrendsError;

  const coverageGaps = useMemo(() => {
    const gaps = coverageData?.gaps ?? [];
    return {
      total: gaps.length,
      withGaps: gaps.filter((g) => g.has_gap).length,
      noTests: gaps.filter((g) => g.gap_type === "no_tests").length,
    };
  }, [coverageData]);

  const failureCategories = useMemo<FailureCategoriesData | undefined>(() => {
    if (!rcaData) return undefined;
    const total = rcaData.total_failures ?? 0;
    const flatten = (clusters: Array<{ tests?: string[] }> | undefined): string[] => {
      if (!clusters) return [];
      const seen = new Set<string>();
      const out: string[] = [];
      for (const c of clusters) {
        for (const t of c.tests ?? []) {
          if (t && !seen.has(t)) {
            seen.add(t);
            out.push(t);
            if (out.length >= 3) return out;
          }
        }
      }
      return out;
    };
    const make = (count: number, clusters: Array<{ tests?: string[] }> | undefined): RcaCategory => ({
      count,
      pct: total > 0 ? (count / total) * 100 : 0,
      topTests: flatten(clusters),
    });
    return {
      defects: make(rcaData.defect_count ?? 0, rcaData.top_defects),
      flakes: make(rcaData.flake_count ?? 0, rcaData.top_flakes),
      environment: make(rcaData.env_count ?? 0, rcaData.top_env),
      unknown: make(rcaData.unknown_count ?? 0, rcaData.top_unknown),
      total,
    };
  }, [rcaData]);

  return (
    <DashboardContext.Provider value={{
      overview,
      analytics,
      coverageGaps,
      coverage,
      failureCategories,
      systemHealth,
      sprintTrends,
      isLoading: overviewLoading || analyticsLoading || coverageLoading || coverageWidgetLoading || rcaLoading || systemHealthLoading || sprintTrendsLoading,
      isInitialLoading: overviewLoading || analyticsLoading || coverageLoading || coverageWidgetLoading || rcaLoading || systemHealthLoading || sprintTrendsLoading,
      isOverviewLoading: overviewLoading,
      isAnalyticsLoading: analyticsLoading,
      isCoverageLoading: coverageLoading || coverageWidgetLoading,
      isFailureCategoriesLoading: rcaLoading,
      isSystemHealthLoading: systemHealthLoading,
      isSprintTrendsLoading: sprintTrendsLoading,
      error: firstError as Error | null,
    }}>
      {children}
    </DashboardContext.Provider>
  );
}
