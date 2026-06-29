// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";

// Mock the dashboard provider
vi.mock("@/components/dashboard/DashboardProvider", () => ({
  DashboardProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useDashboard: () => ({
    overview: null,
    analytics: null,
    coverage: null,
    failureCategories: null,
    systemHealth: { status: "ok" },
    sprintTrends: [],
    isLoading: false,
    isInitialLoading: false,
    isOverviewLoading: false,
    isAnalyticsLoading: false,
    isCoverageLoading: false,
    isFailureCategoriesLoading: false,
    isSystemHealthLoading: false,
    isSprintTrendsLoading: false,
    error: null,
  }),
}));

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("tab=cost"),
  useRouter: () => ({ push: mockPush }),
  useSelectedLayoutSegment: () => null,
}));

// Mock child components to avoid complex rendering
vi.mock("@/components/dashboard/CostTrendCard", () => ({
  CostTrendCard: () => <div data-testid="cost-trend-card">Cost Trend</div>,
}));
vi.mock("@/components/dashboard/CostBreakdownCard", () => ({
  CostBreakdownCard: () => <div data-testid="cost-breakdown-card">Cost Breakdown</div>,
}));
vi.mock("@/components/dashboard/CostByModelCard", () => ({
  CostByModelCard: () => <div data-testid="cost-by-model-card">Cost by Model</div>,
}));
vi.mock("@/components/dashboard/TokenUsageHeatmapCard", () => ({
  TokenUsageHeatmapCard: () => <div data-testid="token-usage-heatmap">Token Usage</div>,
}));
vi.mock("@/components/dashboard/ProviderFailoverCard", () => ({
  ProviderFailoverCard: () => <div data-testid="provider-failover-card">Provider Failover</div>,
}));
vi.mock("@/components/dashboard/UsageStream", () => ({
  UsageStream: () => <div data-testid="usage-stream">Usage Stream</div>,
}));
vi.mock("@/components/dashboard/SystemHealthBar", () => ({
  SystemHealthBar: () => <div data-testid="system-health-bar">Health</div>,
}));
vi.mock("@/components/dashboard/NotificationBell", () => ({
  NotificationBell: () => null,
}));
vi.mock("@/components/dashboard/DashboardSkeleton", () => ({
  DashboardSkeleton: () => <div>Loading...</div>,
}));

// Mock all testing-specific cards that should NOT appear in cost tab
vi.mock("@/components/dashboard/SprintTrends", () => ({
  SprintTrends: () => <div data-testid="testing-card">SHOULD NOT RENDER</div>,
}));
vi.mock("@/components/dashboard/SelfHealingCard", () => ({
  SelfHealingCard: () => <div data-testid="testing-card">SHOULD NOT RENDER</div>,
}));
vi.mock("@/components/dashboard/LogsCard", () => ({
  LogsCard: () => <div data-testid="testing-card">SHOULD NOT RENDER</div>,
}));

describe("Cost Dashboard Tab", () => {
  it("renders cost trend card", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("cost-trend-card")).toBeDefined();
    });
  });

  it("renders cost breakdown card", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("cost-breakdown-card")).toBeDefined();
    });
  });

  it("renders cost by model card", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("cost-by-model-card")).toBeDefined();
    });
  });

  it("renders token usage heatmap card", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("token-usage-heatmap")).toBeDefined();
    });
  });

  it("renders provider failover card", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("provider-failover-card")).toBeDefined();
    });
  });

  it("renders usage stream", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("usage-stream")).toBeDefined();
    });
  });

  it("does not render testing-specific cards (SprintTrends, SelfHealing, Logs)", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      const testingCards = screen.queryAllByTestId("testing-card");
      expect(testingCards.length).toBe(0);
    });
  });

  it("shows role dropdown with admin option", async () => {
    const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");
    render(<DashboardPage />);
    await waitFor(() => {
      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toBeDefined();
      const options = Array.from(dropdown.querySelectorAll("option")).map((o) => o.value);
      expect(options).toContain("admin");
    });
  });
});


