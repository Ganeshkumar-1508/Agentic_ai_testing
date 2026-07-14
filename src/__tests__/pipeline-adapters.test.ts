import { describe, it, expect } from "vitest";
import {
  toJobSpecFromPipelineQuickTest,
  toJobSpecFromChatComposer,
  toJobSpecFromAgentRun,
} from "@/lib/adapters/job-spec";

// ---------------------------------------------------------------------------
// Pipeline quick-test adapter
// ---------------------------------------------------------------------------

describe("toJobSpecFromPipelineQuickTest", () => {
  it("converts a minimal payload with requirements to prompt", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "Add tests for auth API",
      repo_url: "https://github.com/acme/api",
      branch: "main",
    });
    expect(spec.prompt).toBe("Add tests for auth API");
    expect(spec.repo_url).toBe("https://github.com/acme/api");
    expect(spec.branch).toBe("main");
    expect(spec.tier).toBe(1);
    expect(spec.source).toBe("pipeline-quick-test");
  });

  it("falls back to prompt when requirements is missing", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      prompt: "fallback prompt",
    });
    expect(spec.prompt).toBe("fallback prompt");
  });

  it("defaults repo_url and branch when missing", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "test",
    });
    expect(spec.repo_url).toBe("");
    expect(spec.branch).toBe("main");
  });

  it("clamps tier to 1-3", () => {
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: 0 }).tier).toBe(1);
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: 5 }).tier).toBe(3);
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: 2 }).tier).toBe(2);
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: -1 }).tier).toBe(1);
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: 3 }).tier).toBe(3);
  });

  it("defaults tier to 1 when not a number", () => {
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x" }).tier).toBe(1);
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: "high" }).tier).toBe(1);
  });

  it("moves mode + test_types into test_config", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      mode: "auto",
      test_types: ["unit", "e2e"],
    });
    expect(spec.test_config?.mode).toBe("auto");
    expect(spec.test_config?.test_types).toEqual(["unit", "e2e"]);
  });

  it("supports all three mode values", () => {
    for (const mode of ["auto", "ask", "custom"]) {
      const spec = toJobSpecFromPipelineQuickTest({ requirements: "x", mode });
      expect(spec.test_config?.mode).toBe(mode);
    }
  });

  it("preserves file_contents in test_config", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      file_contents: { "test_x.py": "def test_x(): pass" },
    });
    expect(spec.test_config?.file_contents).toEqual({
      "test_x.py": "def test_x(): pass",
    });
  });

  it("preserves github_repo and repo_provider in test_config", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      github_repo: "acme/api",
      repo_provider: "github",
    });
    expect(spec.test_config?.github_repo).toBe("acme/api");
    expect(spec.test_config?.repo_provider).toBe("github");
  });

  it("handles undefined test_types", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      mode: "auto",
      test_types: undefined,
    });
    expect(spec.test_config?.test_types).toBeUndefined();
  });

  it("handles null test_types", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      test_types: null,
    });
    expect(spec.test_config?.test_types).toBeUndefined();
  });

  it("merges advanced_config into test_config", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      advanced_config: {
        continue_on_failure: true,
        notification_channels: ["slack"],
      },
    });
    expect(spec.test_config?.continue_on_failure).toBe(true);
    expect(spec.test_config?.notification_channels).toEqual(["slack"]);
  });

  it("advanced_config deep merges with existing test_config", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      mode: "auto",
      advanced_config: {
        continue_on_failure: true,
        timeout_seconds: 300,
      },
    });
    expect(spec.test_config?.mode).toBe("auto");
    expect(spec.test_config?.continue_on_failure).toBe(true);
    expect(spec.test_config?.timeout_seconds).toBe(300);
  });

  it("ignores non-object advanced_config", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      advanced_config: "not_an_object",
    });
    expect(spec.test_config?.continue_on_failure).toBeUndefined();
  });

  it("preserves additional_context in test_config", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      additional_context: { user_id: "u-1", priority: "high" },
    });
    expect(spec.test_config?.additional_context).toEqual({
      user_id: "u-1",
      priority: "high",
    });
  });

  it("returns default capabilities", () => {
    const spec = toJobSpecFromPipelineQuickTest({ requirements: "x" });
    expect(spec.capabilities).toContain("read_code");
    expect(spec.capabilities).toContain("write_test_files");
    expect(spec.capabilities).toContain("edit_existing_tests");
    expect(spec.capabilities).toContain("run_tests");
    expect(spec.capabilities).toContain("open_pr");
  });

  it("sets approval and context", () => {
    const spec = toJobSpecFromPipelineQuickTest({ requirements: "x" });
    expect(spec.approval).toEqual({ mode: "review_queue", destination: "github_pr" });
    expect(spec.context?.source).toBe("pipeline-quick-test");
  });

  it("handles empty requirements string", () => {
    const spec = toJobSpecFromPipelineQuickTest({ requirements: "" });
    expect(spec.prompt).toBe("");
  });

  it("handles number requirements by converting to string", () => {
    const spec = toJobSpecFromPipelineQuickTest({ requirements: 42 });
    expect(spec.prompt).toBe("42");
  });
});

// ---------------------------------------------------------------------------
// Chat composer adapter
// ---------------------------------------------------------------------------

describe("toJobSpecFromChatComposer", () => {
  it("converts a minimal payload", () => {
    const spec = toJobSpecFromChatComposer({ prompt: "fix the bug" });
    expect(spec.prompt).toBe("fix the bug");
    expect(spec.source).toBe("chat-page");
    expect(spec.tier).toBe(1);
  });

  it("preserves repo_url and branch", () => {
    const spec = toJobSpecFromChatComposer({
      prompt: "x",
      repo_url: "https://github.com/org/repo",
      branch: "develop",
    });
    expect(spec.repo_url).toBe("https://github.com/org/repo");
    expect(spec.branch).toBe("develop");
  });

  it("defaults branch to main", () => {
    const spec = toJobSpecFromChatComposer({ prompt: "x" });
    expect(spec.branch).toBe("main");
  });

  it("defaults repo_url to empty string", () => {
    const spec = toJobSpecFromChatComposer({ prompt: "x" });
    expect(spec.repo_url).toBe("");
  });

  it("clamps tier to 1-3", () => {
    expect(toJobSpecFromChatComposer({ prompt: "x", tier: 0 }).tier).toBe(1);
    expect(toJobSpecFromChatComposer({ prompt: "x", tier: 5 }).tier).toBe(3);
    expect(toJobSpecFromChatComposer({ prompt: "x", tier: 2 }).tier).toBe(2);
  });

  it("filters capabilities to strings only", () => {
    const spec = toJobSpecFromChatComposer({
      prompt: "x",
      capabilities: ["read_code", 42, null, "write_test_files"],
    });
    expect(spec.capabilities).toEqual(["read_code", "write_test_files"]);
  });

  it("provides default capabilities when none given", () => {
    const spec = toJobSpecFromChatComposer({ prompt: "x" });
    expect(spec.capabilities).toEqual([
      "read_code", "write_test_files", "edit_existing_tests", "run_tests", "open_pr",
    ]);
  });

  it("preserves additional_context in context", () => {
    const spec = toJobSpecFromChatComposer({
      prompt: "x",
      additional_context: { user_id: "u-1" },
    });
    expect(spec.context?.additional_context).toEqual({ user_id: "u-1" });
  });

  it("sets source to chat-page", () => {
    const spec = toJobSpecFromChatComposer({ prompt: "x" });
    expect(spec.context?.source).toBe("chat-page");
  });
});

// ---------------------------------------------------------------------------
// Agent run adapter
// ---------------------------------------------------------------------------

describe("toJobSpecFromAgentRun", () => {
  it("converts a minimal payload", () => {
    const spec = toJobSpecFromAgentRun({ prompt: "fix the bug" });
    expect(spec.prompt).toBe("fix the bug");
    expect(spec.source).toBe("agent-page");
  });

  it("preserves explicit capabilities", () => {
    const spec = toJobSpecFromAgentRun({
      prompt: "x",
      capabilities: ["read_code"],
    });
    expect(spec.capabilities).toEqual(["read_code"]);
  });

  it("drops non-string capabilities", () => {
    const spec = toJobSpecFromAgentRun({
      prompt: "x",
      capabilities: ["read_code", 42, null, "write_test_files"],
    });
    expect(spec.capabilities).toEqual(["read_code", "write_test_files"]);
  });

  it("provides default capabilities when none given", () => {
    const spec = toJobSpecFromAgentRun({ prompt: "x" });
    expect(spec.capabilities).toContain("read_code");
    expect(spec.capabilities).toContain("open_pr");
    expect(spec.capabilities).toHaveLength(5);
  });

  it("preserves additional_context in context", () => {
    const spec = toJobSpecFromAgentRun({
      prompt: "x",
      additional_context: { user_id: "u-1" },
    });
    expect(spec.context?.additional_context).toEqual({ user_id: "u-1" });
  });

  it("preserves repo_url and branch", () => {
    const spec = toJobSpecFromAgentRun({
      prompt: "x",
      repo_url: "https://github.com/org/repo",
      branch: "develop",
    });
    expect(spec.repo_url).toBe("https://github.com/org/repo");
    expect(spec.branch).toBe("develop");
  });

  it("clamps tier to 1-3", () => {
    expect(toJobSpecFromAgentRun({ prompt: "x", tier: 0 }).tier).toBe(1);
    expect(toJobSpecFromAgentRun({ prompt: "x", tier: 5 }).tier).toBe(3);
    expect(toJobSpecFromAgentRun({ prompt: "x", tier: 2 }).tier).toBe(2);
  });

  it("sets source to agent-page in context", () => {
    const spec = toJobSpecFromAgentRun({ prompt: "x" });
    expect(spec.context?.source).toBe("agent-page");
  });

  it("handles empty prompt string", () => {
    const spec = toJobSpecFromAgentRun({ prompt: "" });
    expect(spec.prompt).toBe("");
  });
});
