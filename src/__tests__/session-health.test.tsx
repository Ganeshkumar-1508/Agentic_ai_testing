// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SessionHealthPanel } from "@/components/session/SessionHealthPanel";

const mockHealthData = {
  compressions: { count: 3, tokens_before: 500000, tokens_after: 150000, tokens_saved: 350000, ratio: 70 },
  artifacts: { l0_count: 12 },
  checkpoints: { count: 5, latest: "2026-06-27T10:00:00Z", types: { superstep: 3, before_bash: 1, approval_gate: 1 } },
  token_usage: { records: 8, total_tokens: 25000, total_cost: 0.045 },
};

describe("SessionHealthPanel", () => {
  beforeEach(() => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockHealthData,
      headers: new Headers(),
      status: 200,
      statusText: "OK",
    } as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders compression stat card", async () => {
    render(<SessionHealthPanel sessionId="test-session-1" />);
    await waitFor(() => {
      expect(screen.getByText("70%")).toBeDefined();
    });
  });

  it("renders L0 artifacts count", async () => {
    render(<SessionHealthPanel sessionId="test-session-1" />);
    await waitFor(() => {
      expect(screen.getByText("12")).toBeDefined();
    });
  });

  it("renders checkpoint count", async () => {
    render(<SessionHealthPanel sessionId="test-session-1" />);
    await waitFor(() => {
      expect(screen.getByText("5")).toBeDefined();
    });
  });

  it("renders token usage total", async () => {
    render(<SessionHealthPanel sessionId="test-session-1" />);
    await waitFor(() => {
      expect(screen.getByText((content) => content.includes("25") && content.includes("k"))).toBeDefined();
    });
  });

  it("shows no session state when sessionId is null", () => {
    render(<SessionHealthPanel sessionId={null} />);
    expect(screen.getByText("No session selected")).toBeDefined();
  });

  it("renders checkpoint type badges", async () => {
    render(<SessionHealthPanel sessionId="test-session-1" />);
    await waitFor(() => {
      expect(screen.getByText(/superstep: 3/)).toBeDefined();
      expect(screen.getByText(/before_bash: 1/)).toBeDefined();
      expect(screen.getByText(/approval_gate: 1/)).toBeDefined();
    });
  });

  it("shows zero state when no data exists", async () => {
    vi.restoreAllMocks();
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        compressions: { count: 0, tokens_before: 0, tokens_after: 0, tokens_saved: 0, ratio: 0 },
        artifacts: { l0_count: 0 },
        checkpoints: { count: 0, latest: null, types: {} },
        token_usage: { records: 0, total_tokens: 0, total_cost: 0 },
      }),
      headers: new Headers(),
      status: 200,
      statusText: "OK",
    } as Response);

    render(<SessionHealthPanel sessionId="test-session-empty" />);
    await waitFor(() => {
      expect(screen.getByText("0%")).toBeDefined();
    });
  });

  it("shows error state on API failure", async () => {
    vi.restoreAllMocks();
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("Network error"));

    render(<SessionHealthPanel sessionId="test-session-err" />);
    await waitFor(() => {
      expect(screen.getByText("Failed to load session health")).toBeDefined();
    });
  });
});
