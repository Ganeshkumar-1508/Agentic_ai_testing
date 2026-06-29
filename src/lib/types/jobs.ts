/**
 * TypeScript types for the C08 JobSpec surface.
 *
 * Mirrors the backend `api/routers/jobs.py` response models. The
 * field names match the wire format exactly so the API client
 * can pass them through with no mapping.
 *
 * Backend reference: `backend/api/routers/jobs.py:45-100`.
 */

export type JobStatus =
  | "queued"
  | "submitted"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "paused";

export type JobTier = 1 | 2 | 3;

export interface JobComment {
  comment_id: string;
  spec_id: string;
  author: string;
  body: string;
  kind: "comment" | "system" | "approval";
  created_at: string;
}

export interface JobSpec {
  spec_id: string;
  run_id: string;
  source: string;
  prompt: string;
  repo_url: string;
  branch: string;
  sha: string;
  tier: JobTier;
  capabilities: string[];
  approval: Record<string, unknown>;
  context: Record<string, unknown>;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  comments: JobComment[];
}

export interface JobSummary {
  spec_id: string;
  prompt: string;
  repo_url: string;
  tier: JobTier;
  status: JobStatus;
  created_at: string;
  latest_run_id: string | null;
  latest_run_status: string | null;
  latest_run_started_at: string | null;
  latest_run_cost_usd: number | null;
  latest_run_duration_s: number | null;
}

export interface JobOutput {
  spec_id: string;
  status: JobStatus;
  /** JSON-encoded text (the orchestrator writes the
   *  evidence-bundle summary as a JSON string). The renderer
   *  JSON-decodes it on demand. */
  summary: string;
  /** JSON-decoded list of artifacts (paths, URLs, etc.). */
  artifacts: Array<Record<string, unknown>>;
  pr_url: string | null;
  cost_usd: number | null;
  duration_s: number | null;
  completed_at: string | null;
}
