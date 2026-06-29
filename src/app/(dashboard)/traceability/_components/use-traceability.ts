"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";
import type {
  Requirement,
  CoverageGap,
  Defect,
  RiskScore,
  MatrixRow,
  TestCase,
} from "./types";

const PROJECT_KEY = "testai.activeProjectId";

function activeProjectId(): string {
  if (typeof window === "undefined") return "default";
  return window.localStorage.getItem(PROJECT_KEY) || "default";
}

function projectQ(qk: readonly unknown[], projectId: string) {
  return [...qk, projectId];
}

export function useRequirements() {
  return useQuery<{ requirements: Requirement[] }>({
    queryKey: ["trace-requirements", activeProjectId()],
    queryFn: () => api.get<{ requirements: Requirement[] }>(`/api/traceability/requirements?project_id=${encodeURIComponent(activeProjectId())}`),
    refetchInterval: 30_000,
  });
}

export function useCoverageGaps() {
  return useQuery<{ gaps: CoverageGap[] }>({
    queryKey: ["trace-gaps", activeProjectId()],
    queryFn: () => api.get<{ gaps: CoverageGap[] }>(`/api/traceability/coverage-gaps?project_id=${encodeURIComponent(activeProjectId())}`),
    refetchInterval: 30_000,
  });
}

export function useMatrix() {
  return useQuery<{ matrix: MatrixRow[] }>({
    queryKey: ["trace-matrix", activeProjectId()],
    queryFn: () => api.get<{ matrix: MatrixRow[] }>(`/api/traceability/matrix?project_id=${encodeURIComponent(activeProjectId())}`),
    refetchInterval: 30_000,
  });
}

export function useDefects() {
  return useQuery<{ defects: Defect[] }>({
    queryKey: ["trace-defects", activeProjectId()],
    queryFn: () => api.get<{ defects: Defect[] }>(`/api/traceability/defects?project_id=${encodeURIComponent(activeProjectId())}`),
    refetchInterval: 60_000,
  });
}

export function useRiskScores() {
  return useQuery<{ scores: RiskScore[] }>({
    queryKey: ["trace-risk", activeProjectId()],
    queryFn: () => api.get<{ scores: RiskScore[] }>(`/api/traceability/risk-score?project_id=${encodeURIComponent(activeProjectId())}`),
    refetchInterval: 60_000,
  });
}

export function useRequirementDetail(id: string | null) {
  return useQuery<{ requirement: Requirement; tests: TestCase[] }>({
    queryKey: ["trace-requirement", id, activeProjectId()],
    queryFn: () => api.get<{ requirement: Requirement; tests: TestCase[] }>(`/api/traceability/matrix/${id}?project_id=${encodeURIComponent(activeProjectId())}`),
    enabled: Boolean(id),
    refetchInterval: 30_000,
  });
}

function invalidateAll(qc: ReturnType<typeof useQueryClient>, projectId: string) {
  qc.invalidateQueries({ queryKey: projectQ(["trace-requirements"], projectId) });
  qc.invalidateQueries({ queryKey: projectQ(["trace-gaps"], projectId) });
  qc.invalidateQueries({ queryKey: projectQ(["trace-matrix"], projectId) });
  qc.invalidateQueries({ queryKey: projectQ(["trace-risk"], projectId) });
  qc.invalidateQueries({ queryKey: projectQ(["trace-defects"], projectId) });
  qc.invalidateQueries({ queryKey: projectQ(["trace-requirement"], projectId) });
}

export function useCreateRequirement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      title: string;
      description?: string;
      priority?: string;
      project_id?: string;
    }) =>
      api.post<{ requirement: Requirement }>("/api/traceability/requirements", {
        ...body,
        project_id: body.project_id ?? activeProjectId(),
      }),
    onSuccess: () => invalidateAll(qc, activeProjectId()),
  });
}

export function useUpdateRequirement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { id: string; title?: string; status?: string; project_id?: string }) =>
      api.put<{ status: string }>("/api/traceability/requirements", {
        ...body,
        project_id: body.project_id ?? activeProjectId(),
      }),
    onSuccess: () => invalidateAll(qc, activeProjectId()),
  });
}

export function useDeleteRequirement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { id: string; project_id?: string }) =>
      api.delete<{ status: string }>("/api/traceability/requirements", {
        data: { ...body, project_id: body.project_id ?? activeProjectId() },
      }),
    onSuccess: () => invalidateAll(qc, activeProjectId()),
  });
}

export function useLinkTest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      requirement_id: string;
      test_case_id: string;
      project_id?: string;
    }) =>
      api.post<{ status: string }>("/api/traceability/link", {
        ...body,
        project_id: body.project_id ?? activeProjectId(),
      }),
    onSuccess: () => invalidateAll(qc, activeProjectId()),
  });
}

export function useUnlinkTest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      requirement_id: string;
      test_case_id: string;
      project_id?: string;
    }) =>
      api.delete<{ status: string }>("/api/traceability/unlink", {
        data: { ...body, project_id: body.project_id ?? activeProjectId() },
      }),
    onSuccess: () => invalidateAll(qc, activeProjectId()),
  });
}

export function useGenerateTests() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { requirement_ids: string[]; project_id?: string }) =>
      api.post<{
        generated: number;
        tests: Array<{ requirement_id: string; title: string; saved: boolean }>;
      }>("/api/traceability/generate", {
        ...body,
        project_id: body.project_id ?? activeProjectId(),
      }),
    onSuccess: () => invalidateAll(qc, activeProjectId()),
  });
}
