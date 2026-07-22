// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Mocks ─────────────────────────────────────────────────────────
const mockGet = vi.fn();

vi.mock("@/lib/api/api-client", () => ({
  api: { get: (...a: any[]) => mockGet(...a), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

const mockToast = { success: vi.fn(), error: vi.fn() };
vi.mock("sonner", () => ({ toast: mockToast }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Mock SessionBrowser to avoid deep dependency chain
vi.mock("@/components/settings/SessionBrowser", () => ({
  SessionBrowser: () => <div data-testid="session-browser">Session Browser</div>,
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue({ hooks: {}, events: [], plugins: [], jobs: [], subagents: [], sessions_total: 0, total_tokens: 0, total_cost: 0 });
});

// ── Tests ─────────────────────────────────────────────────────────
describe("Admin Page", () => {
  it("renders the admin heading", async () => {
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Admin")).toBeDefined();
    });
  });

  it("renders all 5 tab buttons", async () => {
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Hooks")).toBeDefined();
      expect(screen.getByText("Plugins")).toBeDefined();
      expect(screen.getByText("Cron Jobs")).toBeDefined();
      expect(screen.getByText("Swarm")).toBeDefined();
      expect(screen.getByText("Sessions")).toBeDefined();
    });
  });

  it("defaults to Hooks tab", async () => {
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Registered Hooks")).toBeDefined();
    });
  });

  it("switches to Plugins tab on click", async () => {
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Plugins")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Plugins"));

    await waitFor(() => {
      expect(screen.getByText("Installed Plugins")).toBeDefined();
    });
  });

  it("switches to Cron Jobs tab on click", async () => {
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Cron Jobs")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Cron Jobs"));

    await waitFor(() => {
      expect(screen.getByText("Cron Jobs")).toBeDefined();
    });
  });

  it("switches to Swarm tab on click", async () => {
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Swarm")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Swarm"));

    await waitFor(() => {
      expect(screen.getByText("Active Subagents")).toBeDefined();
    });
  });

  it("switches to Sessions tab and renders SessionBrowser", async () => {
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Sessions")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Sessions"));

    await waitFor(() => {
      expect(screen.getByTestId("session-browser")).toBeDefined();
    });
  });

  it("shows empty state for Hooks when no hooks registered", async () => {
    mockGet.mockResolvedValue({ hooks: {}, events: [] });
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("No hooks registered")).toBeDefined();
    });
  });

  it("shows empty state for Plugins when none installed", async () => {
    mockGet.mockResolvedValue({ plugins: [] });
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await userEvent.click(screen.getByText("Plugins"));

    await waitFor(() => {
      expect(screen.getByText("No plugins installed")).toBeDefined();
    });
  });

  it("shows empty state for Cron when no jobs", async () => {
    mockGet.mockResolvedValue({ jobs: [] });
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await userEvent.click(screen.getByText("Cron Jobs"));

    await waitFor(() => {
      expect(screen.getByText("No cron jobs scheduled")).toBeDefined();
    });
  });

  it("shows empty state for Swarm when no subagents", async () => {
    mockGet.mockResolvedValue({ subagents: [], sessions_total: 0, total_tokens: 0, total_cost: 0 });
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await userEvent.click(screen.getByText("Swarm"));

    await waitFor(() => {
      expect(screen.getByText("No subagents running")).toBeDefined();
    });
  });

  it("displays hooks when registered", async () => {
    mockGet.mockResolvedValueOnce({ hooks: { "run:completed": ["on_complete_handler"] }, events: [] });
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("run:completed")).toBeDefined();
      expect(screen.getByText("1 handler(s)")).toBeDefined();
    });
  });

  it("displays plugins when installed", async () => {
    mockGet.mockResolvedValue({ plugins: [{ name: "test-plugin", version: "1.0.0" }] });
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await userEvent.click(screen.getByText("Plugins"));

    await waitFor(() => {
      expect(screen.getByText("test-plugin")).toBeDefined();
      expect(screen.getByText("v1.0.0")).toBeDefined();
    });
  });

  it("displays swarm stats", async () => {
    mockGet.mockResolvedValue({ subagents: [], sessions_total: 42, total_tokens: 12345, total_cost: 0.5678 });
    const { default: AdminPage } = await import("@/app/(dashboard)/admin/page");
    render(<AdminPage />, { wrapper });

    await userEvent.click(screen.getByText("Swarm"));

    await waitFor(() => {
      expect(screen.getByText("42")).toBeDefined();
      expect(screen.getByText("12,345")).toBeDefined();
      expect(screen.getByText("$0.5678")).toBeDefined();
    });
  });
});
