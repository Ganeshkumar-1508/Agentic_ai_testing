// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { CompactionSection } from "@/components/observability/CompactionSection";

const baseStatus = {
  threshold_percent: 0.85,
  default_threshold_percent: 0.85,
  env_var: "TESTAI_COMPACTION_THRESHOLD",
  context_length: 1_048_576,
  model: "hermes-grok-4.3",
  threshold_tokens: 891_290,
  compactions_total: 3,
  last_before_tokens: 920_000,
  last_after_tokens: 180_000,
  last_saved_tokens: 740_000,
  last_at: new Date().toISOString(),
};

describe("CompactionSection", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = global.fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders the threshold progress bar at 85%", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => baseStatus,
    } as Response) as typeof fetch;

    render(<CompactionSection />);
    await waitFor(() => {
      expect(screen.getByText("Context compaction")).toBeDefined();
    });
    expect(screen.getByText("85%")).toBeDefined();
    expect(screen.getByText("1.05M")).toBeDefined();
    expect(screen.getByText("hermes-grok-4.3")).toBeDefined();
  });

  it("shows the env override badge when threshold differs from default", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...baseStatus, threshold_percent: 0.92, default_threshold_percent: 0.85 }),
    } as Response) as typeof fetch;

    render(<CompactionSection />);
    await waitFor(() => {
      expect(screen.getByText("env override")).toBeDefined();
    });
    expect(screen.getByText(/override active/)).toBeDefined();
  });

  it("shows the last compression before/after/saved tokens", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => baseStatus,
    } as Response) as typeof fetch;

    render(<CompactionSection />);
    await waitFor(() => {
      expect(screen.getByText("Last compaction")).toBeDefined();
    });
    expect(screen.getByText("920.0K")).toBeDefined();
    expect(screen.getByText("180.0K")).toBeDefined();
    expect(screen.getByText(/saved 740.0K tokens/)).toBeDefined();
  });

  it("shows the empty-state when no compressor is configured", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...baseStatus,
        context_length: null,
        model: null,
        threshold_tokens: null,
        last_before_tokens: null,
        last_after_tokens: null,
        last_saved_tokens: null,
        last_at: null,
      }),
    } as Response) as typeof fetch;

    render(<CompactionSection />);
    await waitFor(() => {
      expect(screen.getByText("No context compressor configured")).toBeDefined();
    });
  });

  it("shows the error message on fetch failure", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down")) as typeof fetch;

    render(<CompactionSection />);
    await waitFor(() => {
      expect(screen.getByText("Compaction status unavailable")).toBeDefined();
    });
  });
});
