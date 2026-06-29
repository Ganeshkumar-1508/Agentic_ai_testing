// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SessionTimeline } from "@/components/session/SessionTimeline";

const mockTimelineData = {
  spans: [
    { type: "user", label: "User", started_at: "2026-06-27T10:00:00Z", duration_ms: 0, cost_usd: 0, status: "completed", tokens: 0, preview: "Hello agent" },
    { type: "tool_call", label: "bash", started_at: "2026-06-27T10:00:01Z", duration_ms: 2500, cost_usd: 0.0002, status: true, tokens: 150 },
    { type: "llm_response", label: "LLM Response", started_at: "2026-06-27T10:00:05Z", duration_ms: 0, cost_usd: 0.001, status: "completed", tokens: 500, preview: "Here is the result..." },
  ],
  token_usage: [
    { timestamp: "2026-06-27T10:00:01Z", tokens: 150, cost_usd: 0.0002, model: "gpt-4" },
    { timestamp: "2026-06-27T10:00:05Z", tokens: 500, cost_usd: 0.001, model: "gpt-4" },
  ],
};

describe("SessionTimeline", () => {
  beforeEach(() => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockTimelineData,
      headers: new Headers(),
      status: 200,
      statusText: "OK",
    } as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders timeline heading", async () => {
    render(<SessionTimeline sessionId="test-session" />);
    await waitFor(() => {
      expect(screen.getByText("Session Timeline")).toBeDefined();
    });
  });

  it("renders event count", async () => {
    render(<SessionTimeline sessionId="test-session" />);
    await waitFor(() => {
      expect(screen.getByText("3 events")).toBeDefined();
    });
  });

  it("renders total cost", async () => {
    render(<SessionTimeline sessionId="test-session" />);
    await waitFor(() => {
      expect(screen.getByText(/\$0.0012/)).toBeDefined();
    });
  });

  it("renders total tokens", async () => {
    render(<SessionTimeline sessionId="test-session" />);
    await waitFor(() => {
      expect(screen.getByText(/650 tok/)).toBeDefined();
    });
  });

  it("renders filter buttons", async () => {
    render(<SessionTimeline sessionId="test-session" />);
    await waitFor(() => {
      expect(screen.getByText("All")).toBeDefined();
      expect(screen.getByText("LLM")).toBeDefined();
      expect(screen.getByText("Tools")).toBeDefined();
      expect(screen.getByText("User")).toBeDefined();
    });
  });

  it("shows no session state when sessionId is null", () => {
    render(<SessionTimeline sessionId={null} />);
    expect(screen.getByText("No timeline events for this session")).toBeDefined();
  });

  it("shows token burn chart", async () => {
    render(<SessionTimeline sessionId="test-session" />);
    await waitFor(() => {
      expect(screen.getByText("Token Burn")).toBeDefined();
    });
  });

  it("shows error state on API failure", async () => {
    vi.restoreAllMocks();
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("Network error"));

    render(<SessionTimeline sessionId="test-session-err" />);
    await waitFor(() => {
      expect(screen.getByText("Failed to load timeline")).toBeDefined();
    });
  });

  it("shows empty state when no spans", async () => {
    vi.restoreAllMocks();
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ spans: [], token_usage: [] }),
      headers: new Headers(),
      status: 200,
      statusText: "OK",
    } as Response);

    render(<SessionTimeline sessionId="test-session-empty" />);
    await waitFor(() => {
      expect(screen.getByText("No timeline events for this session")).toBeDefined();
    });
  });
});
