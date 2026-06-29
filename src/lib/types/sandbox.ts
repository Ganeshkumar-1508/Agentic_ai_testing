"use client";

export interface SandboxInfo {
  session_id: string;
  container_id: string;
  workspace_dir: string;
  uptime_seconds: number;
  idle_seconds: number;
  is_running: boolean;
}

export interface SandboxResourceUsage {
  cpu_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  disk_used_mb: number;
  disk_total_mb: number;
  network_kbps: number;
}

export interface SandboxFile {
  name: string;
  path: string;
  type: "file" | "folder";
  size?: number;
  testStatus?: "pass" | "fail" | "pending";
  icon?: string;
}

export interface SandboxPort {
  container_port: number;
  host_port: number;
  label?: string;
}

export interface SandboxDependency {
  name: string;
  version: string;
}

export interface SandboxArtifact {
  name: string;
  path: string;
  size_bytes: number;
  mime_type: string;
}

export interface SandboxFlakyTest {
  test_name: string;
  total_runs: number;
  pass_count: number;
  fail_count: number;
  flaky_score: number;
  is_quarantined: boolean;
}

export interface SandboxEvent {
  timestamp?: string;
  type: "info" | "exec" | "pass" | "fail" | "agent" | "tool";
  message: string;
  detail?: string;
}
