import { describe, it, expect } from "vitest";
import type { JobSpec, JobSummary, JobOutput, JobStatus } from "@/lib/types/jobs";

describe("JobSpec types", () => {
  it("accepts the canonical C08 response shape", () => {
    const s: JobSpec = {
      spec_id: "spec-1",
      run_id: "run-1",
      source: "chat",
      prompt: "Generate tests for the auth API",
      repo_url: "https://github.com/acme/api",
      branch: "main",
      sha: "abc123",
      tier: 1,
      capabilities: ["write_test_files", "open_pr"],
      approval: {},
      context: { session_id: "sess-1" },
      status: "running",
      created_at: "2026-06-21T00:00:00Z",
      started_at: "2026-06-21T00:00:01Z",
      completed_at: null,
      error: null,
      comments: [
        {
          comment_id: "c1",
          spec_id: "spec-1",
          author: "user",
          body: "Looks good",
          kind: "comment",
          created_at: "2026-06-21T00:00:02Z",
        },
      ],
    };
    expect(s.tier).toBe(1);
    expect(s.comments[0].kind).toBe("comment");
  });

  it("accepts all 7 C08 statuses", () => {
    const statuses: JobStatus[] = [
      "queued",
      "submitted",
      "running",
      "completed",
      "failed",
      "cancelled",
      "paused",
    ];
    for (const st of statuses) {
      const s: JobSpec = {
        spec_id: "x",
        run_id: "",
        source: "api",
        prompt: "",
        repo_url: "",
        branch: "main",
        sha: "",
        tier: 1,
        capabilities: [],
        approval: {},
        context: {},
        status: st,
        created_at: "",
        started_at: null,
        completed_at: null,
        error: null,
        comments: [],
      };
      expect(s.status).toBe(st);
    }
  });
});

describe("JobSummary types", () => {
  it("accepts the list endpoint shape (Q10)", () => {
    const s: JobSummary = {
      spec_id: "spec-1",
      prompt: "p",
      repo_url: "r",
      tier: 1,
      status: "completed",
      created_at: "2026-06-21T00:00:00Z",
      latest_run_id: "run-1",
      latest_run_status: "ok",
      latest_run_started_at: "2026-06-21T00:00:01Z",
      latest_run_cost_usd: 0.42,
      latest_run_duration_s: 12.5,
    };
    expect(s.latest_run_cost_usd).toBe(0.42);
  });
});

describe("JobOutput types", () => {
  it("accepts the output endpoint shape", () => {
    const o: JobOutput = {
      spec_id: "spec-1",
      status: "completed",
      summary: JSON.stringify({ result: "ok", files: ["a.test.ts", "b.test.ts"] }),
      artifacts: [{ id: "art-1", kind: "test_file", url: "/api/artifacts/art-1" }],
      pr_url: "https://github.com/example/repo/pull/42",
      cost_usd: 0.42,
      duration_s: 12.5,
      completed_at: "2026-06-21T00:01:00Z",
    };
    expect(o.artifacts[0].kind).toBe("test_file");
    expect(o.cost_usd).toBe(0.42);
  });
});
