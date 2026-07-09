/**
 * JobSpec adapters — frontend helpers for the canonical
 * `POST /api/jobs` surface.
 *
 * C08 Q7 step 2: the legacy `/api/pipeline/from-requirements`
 * and `/api/agent/run` HTTP endpoints have been hard-deleted
 * along with the backend `legacy_adapters.py` module. The
 * functions here are the *frontend* counterparts: they take
 * the legacy payload shapes (from the pipeline store's
 * quick-test form and the agent page's run form) and convert
 * them to the canonical JobSpecRequest shape. Use them in
 * the pipeline store and the agent page.
 *
 * These are pure functions; they don't make HTTP calls.
 * After converting, the caller posts the result to
 * `/api/jobs`.
 */
import type { JobSpec, JobStatus, JobTier } from "@/lib/types/jobs";

export interface JobSpecRequest {
  spec_id?: string;
  source?: string;
  prompt: string;
  repo_url?: string;
  branch?: string;
  sha?: string;
  tier?: JobTier;
  capabilities?: string[];
  approval?: Record<string, unknown>;
  context?: Record<string, unknown>;
  test_config?: Record<string, unknown>;
}

/**
 * Convert a "quick test" pipeline payload (from the pipeline
 * store's quick-test form) to a JobSpecRequest.
 *
 * The quick-test payload has:
 *   - requirements (string)
 *   - repo_url
 *   - branch
 *   - mode ("auto" | "ask" | "custom")
 *   - test_types (string[])
 *   - tier (1 | 2 | 3, optional)
 *   - file_contents (record of filename -> content, optional)
 *
 * Returns a JobSpecRequest with:
 *   - prompt = requirements
 *   - repo_url, branch
 *   - context.test_config = the rest (mode, test_types, files)
 */
export function toJobSpecFromPipelineQuickTest(
  payload: Record<string, unknown>,
): JobSpecRequest {
  const testConfig: Record<string, unknown> = {};
  if (payload.mode !== undefined) testConfig.mode = payload.mode;
  if (Array.isArray(payload.test_types)) {
    testConfig.test_types = payload.test_types;
  }
  if (payload.file_contents && typeof payload.file_contents === "object") {
    testConfig.file_contents = payload.file_contents;
  }
  if (payload.github_repo !== undefined) {
    testConfig.github_repo = payload.github_repo;
  }
  if (payload.repo_provider !== undefined) {
    testConfig.repo_provider = payload.repo_provider;
  }
  if (payload.additional_context !== undefined) {
    testConfig.additional_context = payload.additional_context;
  }
  if (payload.advanced_config && typeof payload.advanced_config === "object") {
    Object.assign(testConfig, payload.advanced_config);
  }

  const tier = typeof payload.tier === "number"
    ? Math.max(1, Math.min(3, payload.tier)) as JobTier
    : 1;

  return {
    source: "pipeline-quick-test",
    prompt: String(payload.requirements ?? payload.prompt ?? ""),
    repo_url: payload.repo_url ? String(payload.repo_url) : "",
    branch: payload.branch ? String(payload.branch) : "main",
    tier,
    capabilities: ["read_code", "write_test_files", "edit_existing_tests", "run_tests", "open_pr"],
    approval: { mode: "review_queue", destination: "github_pr" },
    context: { source: "pipeline-quick-test" },
    test_config: testConfig,
  };
}

/**
 * Convert a chat-composer payload (from the /chat page's
 * composer) to a JobSpecRequest.
 *
 * The chat-composer payload has:
 *   - prompt (string, required)
 *   - repo_url
 *   - branch
 *   - tier (1 | 2 | 3, optional)
 *   - capabilities (string[], optional)
 *   - additional_context (any)
 *
 * Returns a JobSpecRequest with the same shape.
 */
export function toJobSpecFromChatComposer(
  payload: Record<string, unknown>,
): JobSpecRequest {
  const tier = typeof payload.tier === "number"
    ? Math.max(1, Math.min(3, payload.tier)) as JobTier
    : 1;

  const capabilities = Array.isArray(payload.capabilities)
    ? (payload.capabilities as string[]).filter((c) => typeof c === "string")
    : ["read_code", "write_test_files", "edit_existing_tests", "run_tests", "open_pr"];

  const context: Record<string, unknown> = { source: "chat-page" };
  if (payload.additional_context !== undefined) {
    context.additional_context = payload.additional_context;
  }

  return {
    source: "chat-page",
    prompt: String(payload.prompt ?? ""),
    repo_url: payload.repo_url ? String(payload.repo_url) : "",
    branch: payload.branch ? String(payload.branch) : "main",
    tier,
    capabilities,
    approval: { mode: "review_queue", destination: "github_pr" },
    context,
  };
}

/**
 * Convert an agent-run payload (from the /agents page) to a JobSpecRequest.
 *
 * The agent-run payload has:
 *   - prompt (string, required)
 *   - repo_url
 *   - branch
 *   - tier (1 | 2 | 3, optional)
 *   - capabilities (string[], optional)
 *   - additional_context (any)
 */
export function toJobSpecFromAgentRun(
  payload: Record<string, unknown>,
): JobSpecRequest {
  const tier = typeof payload.tier === "number"
    ? Math.max(1, Math.min(3, payload.tier)) as JobTier
    : 1;

  const capabilities = Array.isArray(payload.capabilities)
    ? (payload.capabilities as string[]).filter((c) => typeof c === "string")
    : ["read_code", "write_test_files", "edit_existing_tests", "run_tests", "open_pr"];

  const context: Record<string, unknown> = { source: "agent-page" };
  if (payload.additional_context !== undefined) {
    context.additional_context = payload.additional_context;
  }

  return {
    source: "agent-page",
    prompt: String(payload.prompt ?? ""),
    repo_url: payload.repo_url ? String(payload.repo_url) : "",
    branch: payload.branch ? String(payload.branch) : "main",
    tier,
    capabilities,
    approval: { mode: "review_queue", destination: "github_pr" },
    context,
  };
}
