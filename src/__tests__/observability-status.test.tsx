// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ObservabilityStatus } from "@/components/observability/ObservabilityStatus";

const baseStatus = {
  enabled: true,
  available: true,
  endpoint: "http://otel.example:4317",
  service_name: "testai-harness",
  service_version: "1.0.0",
  span_counts: {
    chat: 142,
    execute_tool: 87,
    subagent_invoke: 12,
    kanban_transition: 38,
  },
  last_span_at: new Date().toISOString(),
};

describe("ObservabilityStatus", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = global.fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders the status header with ok tone when enabled + available", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => baseStatus,
    } as Response) as typeof fetch;

    render(<ObservabilityStatus />);
    await waitFor(() => {
      expect(screen.getByText("OpenTelemetry")).toBeDefined();
    });
    expect(screen.getByText("http://otel.example:4317")).toBeDefined();
    expect(screen.getByText("testai-harness")).toBeDefined();
    expect(screen.getByText("v1.0.0")).toBeDefined();
  });

  it("shows a warn banner when OTel is disabled", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...baseStatus, enabled: false, available: false }),
    } as Response) as typeof fetch;

    render(<ObservabilityStatus />);
    await waitFor(() => {
      expect(screen.getByText("OpenTelemetry is not enabled")).toBeDefined();
    });
  });

  it("shows a danger banner when OTel is enabled but unavailable", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...baseStatus, enabled: true, available: false }),
    } as Response) as typeof fetch;

    render(<ObservabilityStatus />);
    await waitFor(() => {
      expect(screen.getByText("OTel SDK not available")).toBeDefined();
    });
  });

  it("renders a count card for each known operation", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => baseStatus,
    } as Response) as typeof fetch;

    render(<ObservabilityStatus />);
    await waitFor(() => {
      expect(screen.getByText("LLM chat")).toBeDefined();
      expect(screen.getByText("Tool calls")).toBeDefined();
      expect(screen.getByText("Subagents")).toBeDefined();
      expect(screen.getByText("Kanban transitions")).toBeDefined();
    });
  });

  it("shows the error message on fetch failure", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down")) as typeof fetch;

    render(<ObservabilityStatus />);
    await waitFor(() => {
      expect(screen.getByText("Observability status unavailable")).toBeDefined();
      expect(screen.getByText("network down")).toBeDefined();
    });
  });
});
