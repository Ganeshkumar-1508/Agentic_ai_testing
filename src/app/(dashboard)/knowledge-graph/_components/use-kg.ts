"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/api-client";
import type {
  GraphListResponse,
  GraphDetailResponse,
  FileContentResponse,
} from "./types";

export function useGraphs() {
  return useQuery({
    queryKey: ["kg-graphs"],
    queryFn: () => api.get<GraphListResponse>("/api/knowledge-graph/recent"),
    refetchInterval: 60_000,
  });
}

export function useGraph(id: string | null) {
  return useQuery({
    queryKey: ["kg-graph", id],
    queryFn: () => api.get<GraphDetailResponse>(`/api/knowledge-graph/${id}`),
    enabled: Boolean(id),
    refetchInterval: 120_000,
  });
}

export function useFileContent(graphId: string | null, path: string | null) {
  return useQuery({
    queryKey: ["kg-file-content", graphId, path],
    queryFn: () => api.get<FileContentResponse>(
      `/api/knowledge-graph/${graphId}/file-content?path=${encodeURIComponent(path ?? "")}`
    ),
    enabled: Boolean(graphId && path),
    staleTime: 5 * 60_000,
  });
}
