import { describe, it, expect } from "vitest";
import {
  toJobSpecFromPipelineQuickTest,
  toJobSpecFromAgentRun,
} from "@/lib/adapters/job-spec";

describe("toJobSpecFromPipelineQuickTest", () => {
  it("converts a minimal payload", () => {
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

  it("clamps tier to 1-3", () => {
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: 0 }).tier).toBe(1);
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: 5 }).tier).toBe(3);
    expect(toJobSpecFromPipelineQuickTest({ requirements: "x", tier: 2 }).tier).toBe(2);
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

  it("preserves file_contents", () => {
    const spec = toJobSpecFromPipelineQuickTest({
      requirements: "x",
      file_contents: { "test_x.py": "def test_x(): pass" },
    });
    expect(spec.test_config?.file_contents).toEqual({
      "test_x.py": "def test_x(): pass",
    });
  });
});

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

  it("preserves additional_context in context", () => {
    const spec = toJobSpecFromAgentRun({
      prompt: "x",
      additional_context: { user_id: "u-1" },
    });
    expect(spec.context?.additional_context).toEqual({ user_id: "u-1" });
  });
});
