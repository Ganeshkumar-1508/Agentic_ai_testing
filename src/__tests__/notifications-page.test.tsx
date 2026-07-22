// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Mocks ─────────────────────────────────────────────────────────
const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api/api-client", () => ({
  api: { get: (...a: any[]) => mockGet(...a), post: (...a: any[]) => mockPost(...a), delete: (...a: any[]) => mockDelete(...a) },
}));

const mockToast = { success: vi.fn(), error: vi.fn() };
vi.mock("sonner", () => ({ toast: mockToast }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const mockNotifications = [
  {
    id: "n1", channel: "email", recipient: "user@test.com", subject: "Run completed",
    body: "Pipeline passed", status: "delivered", error: "", source: "pipeline",
    run_id: "run-12345", created_at: "2025-01-15T10:00:00Z", delivered_at: "2025-01-15T10:01:00Z",
  },
  {
    id: "n2", channel: "slack", recipient: "#alerts", subject: "Run failed",
    body: "Test failed", status: "pending", error: "", source: "pipeline",
    run_id: "run-67890", created_at: "2025-01-15T11:00:00Z", delivered_at: "",
  },
  {
    id: "n3", channel: "webhook", recipient: "", subject: "Error occurred",
    body: "", status: "failed", error: "Connection refused", source: "alert",
    run_id: "", created_at: "2025-01-15T12:00:00Z", delivered_at: "",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────
describe("Notifications Page", () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({ notifications: mockNotifications, unread: 2 });
    mockPost.mockResolvedValue({});
    mockDelete.mockResolvedValue({});
  });

  it("renders notifications list", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Run completed")).toBeDefined();
      expect(screen.getByText("Run failed")).toBeDefined();
      expect(screen.getByText("Error occurred")).toBeDefined();
    });
  });

  it("shows unread count", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText(/2 unread/)).toBeDefined();
    });
  });

  it("shows Mark All Read button when unread > 0", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Mark All Read")).toBeDefined();
    });
  });

  it("calls mark-all-read API when Mark All Read clicked", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Mark All Read")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Mark All Read"));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/notifications/read-all", {});
    });
  });

  it("shows error toast when mark-all-read fails", async () => {
    mockPost.mockRejectedValue(new Error("fail"));
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Mark All Read")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Mark All Read"));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith("Failed to mark as read");
    });
  });

  it("has per-notification mark-as-read button", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      // Each notification row should have a "Mark as read" button
      const markBtns = screen.getAllByTitle("Mark as read");
      expect(markBtns.length).toBe(3);
    });
  });

  it("calls correct API when individual mark-as-read clicked", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getAllByTitle("Mark as read").length).toBe(3);
    });

    const markBtns = screen.getAllByTitle("Mark as read");
    await userEvent.click(markBtns[0]);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/notifications/n1/read", {});
    });
  });

  it("has per-notification delete button", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      const deleteBtns = screen.getAllByTitle("Delete");
      expect(deleteBtns.length).toBe(3);
    });
  });

  it("shows confirm dialog before deleting notification", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getAllByTitle("Delete").length).toBe(3);
    });

    const deleteBtns = screen.getAllByTitle("Delete");
    await userEvent.click(deleteBtns[0]);

    expect(confirmSpy).toHaveBeenCalledWith("Delete this notification?");
    confirmSpy.mockRestore();
  });

  it("calls delete API when confirmed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getAllByTitle("Delete").length).toBe(3);
    });

    const deleteBtns = screen.getAllByTitle("Delete");
    await userEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/notifications/n1");
    });
    vi.restoreAllMocks();
  });

  it("shows error toast when delete fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockDelete.mockRejectedValue(new Error("fail"));
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getAllByTitle("Delete").length).toBe(3);
    });

    const deleteBtns = screen.getAllByTitle("Delete");
    await userEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith("Failed to delete notification");
    });
    vi.restoreAllMocks();
  });

  it("shows empty state when no notifications", async () => {
    mockGet.mockResolvedValue({ notifications: [], unread: 0 });
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("No notifications yet")).toBeDefined();
    });
  });

  it("shows All caught up when unread is 0", async () => {
    mockGet.mockResolvedValue({ notifications: mockNotifications, unread: 0 });
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText(/All caught up/)).toBeDefined();
    });
  });

  it("hides Mark All Read button when unread is 0", async () => {
    mockGet.mockResolvedValue({ notifications: mockNotifications, unread: 0 });
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.queryByText("Mark All Read")).toBeNull();
    });
  });

  it("shows channel icons for each notification", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("via email")).toBeDefined();
      expect(screen.getByText("via slack")).toBeDefined();
      expect(screen.getByText("via webhook")).toBeDefined();
    });
  });

  it("shows failed badge for error notifications", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("failed")).toBeDefined();
    });
  });

  it("shows pending badge for pending notifications", async () => {
    const { default: NotificationsPage } = await import("@/app/(dashboard)/notifications/page");
    render(<NotificationsPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("pending")).toBeDefined();
    });
  });
});
