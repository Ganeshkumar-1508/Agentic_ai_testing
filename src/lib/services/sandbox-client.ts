"use client";

import { api, apiFetch, BACKEND_URL } from "@/lib/api/api-client";
import type { SandboxInfo, SandboxResourceUsage, SandboxPort, SandboxDependency, SandboxArtifact, SandboxFlakyTest, SandboxEvent } from "@/lib/types/sandbox";

export async function fetchSandboxInfo(sessionId: string): Promise<SandboxInfo | null> {
  try {
    const data = await api.get<{ sandboxes?: SandboxInfo[] }>("/api/sandbox/list");
    if (!data?.sandboxes) return null;
    return data.sandboxes.find((s) => s.session_id === sessionId) || null;
  } catch {
    return null;
  }
}

export async function fetchSandboxResources(sessionId: string): Promise<SandboxResourceUsage | null> {
  try {
    return await api.get<SandboxResourceUsage>(`/api/sandbox/${sessionId}/resources`);
  } catch {
    return null;
  }
}

export async function fetchSandboxPorts(sessionId: string): Promise<SandboxPort[]> {
  try {
    const data = await api.get<{ ports?: SandboxPort[] }>(`/api/sandbox/${sessionId}/ports`);
    return data?.ports || [];
  } catch {
    return [];
  }
}

export async function fetchSandboxDependencies(sessionId: string): Promise<{ dependencies: SandboxDependency[]; total_count: number }> {
  try {
    return await api.get<{ dependencies: SandboxDependency[]; total_count: number }>(`/api/sandbox/${sessionId}/dependencies`);
  } catch {
    return { dependencies: [], total_count: 0 };
  }
}

export async function fetchFlakyTests(sessionId: string): Promise<SandboxFlakyTest[]> {
  try {
    const data = await api.get<{ flaky_tests?: SandboxFlakyTest[] }>(`/api/sandbox/${sessionId}/flaky-tests`);
    return data?.flaky_tests || [];
  } catch {
    return [];
  }
}

export async function fetchSandboxArtifacts(sessionId: string): Promise<SandboxArtifact[]> {
  try {
    const data = await api.get<{ artifacts?: SandboxArtifact[] }>(`/api/sandbox/${sessionId}/artifacts`);
    return data?.artifacts || [];
  } catch {
    return [];
  }
}

export async function fetchSandboxEvents(sessionId: string): Promise<SandboxEvent[]> {
  try {
    const data = await api.get<{ events?: SandboxEvent[] }>(`/api/sandbox/${sessionId}/events`);
    return data?.events || [];
  } catch {
    return [];
  }
}

export async function fetchWorkspaceFiles(sessionId: string, path = "."): Promise<string[]> {
  try {
    const data = await api.get<{ files?: string[] }>(`/api/sandbox/workspace/${sessionId}?path=${encodeURIComponent(path)}`);
    return data?.files || [];
  } catch {
    return [];
  }
}

export async function fetchWorkspaceFileContent(sessionId: string, path: string): Promise<string | null> {
  try {
    const data = await api.get<{ content?: string }>(`/api/sandbox/workspace/${sessionId}/file?path=${encodeURIComponent(path)}`);
    return data?.content || null;
  } catch {
    return null;
  }
}

export async function downloadFile(sessionId: string, path: string): Promise<void> {
  const content = await fetchWorkspaceFileContent(sessionId, path);
  if (!content) return;
  const blob = new Blob([content]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = path.split("/").pop() || "download";
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadWorkspaceArchive(sessionId: string): Promise<void> {
  const a = document.createElement("a");
  a.href = `${BACKEND_URL}/api/sandbox/workspace/${sessionId}/archive`;
  a.download = `sandbox-${sessionId.slice(0, 12)}.tar.gz`;
  a.click();
}

export async function destroySandbox(sessionId: string): Promise<boolean> {
  try {
    const res = await apiFetch(`/api/sandbox/${sessionId}`, { method: "DELETE" });
    return res.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// C4.1 — SandboxSnapshot (E2B / Daytona / Modal / Sprites pattern).
//
// The snapshot is an EXPOSED primitive. The agent / orchestrator / UI
// invokes it explicitly; the backend never auto-snapshots. These
// wrappers hit the HTTP routes registered in
// `backend/api/routers/sandbox.py` (see the 4 new routes:
// `POST /sandbox/{id}/snapshot`, `POST /sandbox/restore`,
// `GET /sandbox/{id}/snapshots`, `GET /sandbox/snapshots`).
// ---------------------------------------------------------------------------


export interface SnapshotInfo {
  status?: string;
  session_id?: string;
  snapshot_id?: string;
  label?: string;
}

export interface SnapshotList {
  session_id?: string;
  snapshots: string[];
  count: number;
}

export async function createSandboxSnapshot(
  sessionId: string,
  label: string = "",
): Promise<SnapshotInfo | null> {
  try {
    return await api.post<SnapshotInfo>(`/api/sandbox/${sessionId}/snapshot`, { label });
  } catch {
    return null;
  }
}

export async function restoreSandboxSnapshot(
  snapshotId: string,
  sessionId?: string,
): Promise<{ status: string; snapshot_id: string; session_id: string } | null> {
  try {
    return await api.post(`/api/sandbox/restore`, { snapshot_id: snapshotId, session_id: sessionId });
  } catch {
    return null;
  }
}

export async function listSandboxSnapshots(sessionId: string): Promise<string[]> {
  try {
    const data = await api.get<SnapshotList>(`/api/sandbox/${sessionId}/snapshots`);
    return data?.snapshots || [];
  } catch {
    return [];
  }
}

export async function listAllSnapshots(): Promise<string[]> {
  try {
    const data = await api.get<SnapshotList>("/api/sandbox/snapshots");
    return data?.snapshots || [];
  } catch {
    return [];
  }
}
