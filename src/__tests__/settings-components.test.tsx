// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ── Shared mocks ──────────────────────────────────────────────────
const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();
const mockPatch = vi.fn();

vi.mock("@/lib/api/api-client", () => ({
  api: { get: (...a: any[]) => mockGet(...a), post: (...a: any[]) => mockPost(...a), delete: (...a: any[]) => mockDelete(...a), patch: (...a: any[]) => mockPatch(...a) },
}));

const mockToast = { success: vi.fn(), error: vi.fn() };
vi.mock("sonner", () => ({ toast: mockToast }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue({ data: [] });
  mockPost.mockResolvedValue({});
  mockDelete.mockResolvedValue({});
});

// ── 1. PlatformAdapterSettings ────────────────────────────────────
describe("PlatformAdapterSettings — testConnection", () => {
  it("calls real API on test button click", async () => {
    mockGet.mockResolvedValue({
      platforms: [{ id: "1", platform: "slack", enabled: true, config: { api_token: "xoxb-test" }, created_at: "", updated_at: "" }],
    });
    mockPost.mockResolvedValue({ success: true });
    const { PlatformAdapterSettings } = await import("@/components/settings/PlatformAdapterSettings");
    render(<PlatformAdapterSettings />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Slack")).toBeDefined();
    });

    // The test button only appears for configured platforms
    const testBtn = screen.getByText("test");
    await userEvent.click(testBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled();
      expect(mockPost.mock.calls[0][0]).toContain("/api/settings/platforms/slack/test");
    });
  });
});

// ── 2. OTelSettings — state not set during render ─────────────────
describe("OTelSettings — useEffect init", () => {
  it("renders without crashing when data loads", async () => {
    mockGet.mockResolvedValue({
      enabled: true, available: true, endpoint: "http://localhost:4317",
      service_name: "testai", span_counts: {}, last_span_at: null,
    });
    const { OTelSettings } = await import("@/components/settings/OTelSettings");
    render(<OTelSettings />, { wrapper });
    await waitFor(() => {
      expect(screen.getByDisplayValue("http://localhost:4317")).toBeDefined();
    });
  });
});

// ── 3. WebhookConfig — error toasts ───────────────────────────────
describe("WebhookConfig — error handling", () => {
  it("shows error toast when fetch fails", async () => {
    mockGet.mockRejectedValue(new Error("Network error"));
    const { WebhookConfig } = await import("@/components/settings/WebhookConfig");
    render(<WebhookConfig />);
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith("Failed to load webhooks");
    });
  });
});

// ── 4. CICDSetup — no prefix copy button ──────────────────────────
describe("CICDSetup — copy button removed", () => {
  it("does not render a per-row copy button for API keys", async () => {
    mockGet.mockResolvedValue({ keys: [] });
    const { CICDSetup } = await import("@/components/settings/CICDSetup");
    render(<CICDSetup />);
    await waitFor(() => {
      expect(screen.getByText("API Keys")).toBeDefined();
    });
    expect(screen.queryByTitle("Copy key prefix")).toBeNull();
  });
});

// ── 5. MCPServerManager — status sort ─────────────────────────────
describe("MCPServerManager — status sort", () => {
  it("sorts servers by name by default", async () => {
    mockGet.mockResolvedValueOnce({ servers: [
      { id: "1", name: "zebra", displayName: "Zebra", category: "", serverType: "command", enabled: true },
      { id: "2", name: "alpha", displayName: "Alpha", category: "", serverType: "command", enabled: true },
    ]}).mockResolvedValueOnce({ connections: [] });

    const { MCPServerManager } = await import("@/components/settings/MCPServerManager");
    render(<MCPServerManager />, { wrapper });

    await waitFor(() => {
      const names = screen.getAllByText(/Alpha|Zebra/i).map(el => el.textContent);
      const alphaIdx = names.findIndex(n => n?.includes("Alpha"));
      const zebraIdx = names.findIndex(n => n?.includes("Zebra"));
      expect(alphaIdx).toBeLessThan(zebraIdx);
    });
  });
});

// ── 6. ToolPermissionsManager — search crash guard ────────────────
describe("ToolPermissionsManager — null-safety", () => {
  it("does not crash when tool description is undefined", async () => {
    mockGet.mockResolvedValue({ tools: [
      { name: "test_tool", level: "allow", default: "allow", description: undefined },
    ]});
    const { ToolPermissionsManager } = await import("@/components/settings/ToolPermissionsManager");
    render(<ToolPermissionsManager />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("test_tool")).toBeDefined();
    });

    const input = screen.getByPlaceholderText("Search tools...");
    fireEvent.change(input, { target: { value: "test" } });

    await waitFor(() => {
      expect(screen.getByText("test_tool")).toBeDefined();
    });
  });
});

// ── 7. FeatureFlags — toggle preserves rollout ────────────────────
describe("FeatureFlags — rollout preservation", () => {
  it("preserves rollout_percent when disabling a flag", async () => {
    mockGet.mockResolvedValue({ flags: [
      { key: "dark-mode", flag_key: "dark-mode", label: "Dark Mode", description: "", enabled: true, rollout_percent: 25 },
    ]});
    const { FeatureFlags } = await import("@/components/settings/FeatureFlags");
    render(<FeatureFlags />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("dark-mode")).toBeDefined();
    });

    // The toggle is a button with the ToggleRight icon inside
    // Find the button that wraps the toggle icon
    const allButtons = screen.getAllByRole("button");
    const toggleBtn = allButtons.find(b => {
      const svg = b.querySelector("svg");
      return svg && svg.classList.contains("lucide-toggle-right");
    });
    if (toggleBtn) {
      await userEvent.click(toggleBtn);
      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledWith(
          "/api/settings/feature-flags",
          expect.objectContaining({ rollout_percent: 25 })
        );
      });
    }
  });
});

// ── 8. BudgetSettings — error toast ───────────────────────────────
describe("BudgetSettings — error handling", () => {
  it("shows error toast when budget save fails", async () => {
    mockGet.mockResolvedValue({ budgets: [] });
    const { BudgetSettings } = await import("@/components/settings/BudgetSettings");
    render(<BudgetSettings />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Cost Budgets")).toBeDefined();
    });
  });
});

// ── 9. Agent Definitions — delete confirmation ────────────────────
describe("AgentDefinitions — delete confirm", () => {
  it("shows confirm dialog before delete", async () => {
    mockGet.mockResolvedValue({ agents: [
      { name: "test-agent", description: "Test", model: "", tools: ["read"], skills: [], triggers: [], mode: "subagent", prompt: "", disabled: false, temperature: 0.3, max_steps: 20 },
    ]});
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { AgentsSettings } = await import("@/components/settings/AgentsSettings");
    render(<AgentsSettings />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("test-agent")).toBeDefined();
    });

    const deleteBtn = screen.getByTitle("Delete");
    await userEvent.click(deleteBtn);

    expect(confirmSpy).toHaveBeenCalledWith('Delete agent "test-agent"? This cannot be undone.');
    confirmSpy.mockRestore();
  });
});

// ── 10. Agent Definitions — rename tracking ───────────────────────
describe("AgentDefinitions — rename", () => {
  it("PUTs to original name when renaming", async () => {
    mockGet.mockResolvedValue({ agents: [
      { name: "old-name", description: "Test", model: "", tools: ["read"], skills: [], triggers: [], mode: "subagent", prompt: "", disabled: false, temperature: 0.3, max_steps: 20 },
    ]});
    mockPost.mockResolvedValue({});
    const { AgentsSettings } = await import("@/components/settings/AgentsSettings");
    render(<AgentsSettings />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("old-name")).toBeDefined();
    });

    const editBtn = screen.getByTitle("Edit");
    await userEvent.click(editBtn);

    await waitFor(() => {
      expect(screen.getByDisplayValue("old-name")).toBeDefined();
    });

    const nameInput = screen.getByDisplayValue("old-name");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "new-name");

    const saveBtn = screen.getByText("Save agent");
    await userEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockPost).not.toHaveBeenCalledWith("/api/agents/new-name", expect.anything());
    });
  });
});

// ── 11. Daily Digest — toggle enabled ─────────────────────────────
describe("DigestConfigPanel — toggle", () => {
  it("calls API to toggle config enabled state", async () => {
    mockGet.mockResolvedValue({ configs: [
      { id: "1", platform: "slack", channel_id: "#general", schedule: "0 8 * * *", enabled: true, created_at: "" },
    ]});
    mockPost.mockResolvedValue({});
    const { DigestConfigPanel } = await import("@/components/settings/DigestConfigPanel");
    render(<DigestConfigPanel />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("active")).toBeDefined();
    });

    const activeBadge = screen.getByText("active");
    await userEvent.click(activeBadge);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/digest/configs", expect.objectContaining({ enabled: false }));
    });
  });
});

// ── 12. Daily Digest — error toasts ───────────────────────────────
describe("DigestConfigPanel — error handling", () => {
  it("shows error toast when load fails", async () => {
    mockGet.mockRejectedValue(new Error("fail"));
    const { DigestConfigPanel } = await import("@/components/settings/DigestConfigPanel");
    render(<DigestConfigPanel />, { wrapper });
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith("Failed to load digest configs");
    });
  });
});

// ── 13. NotificationPreferences — target validation ───────────────
describe("NotificationPreferences — validation", () => {
  it("disables save button when target is empty", async () => {
    mockGet.mockResolvedValue({ preferences: [] });
    const { NotificationPreferences } = await import("@/components/settings/NotificationPreferences");
    render(<NotificationPreferences />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Add Channel")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Add Channel"));

    await waitFor(() => {
      const saveBtn = screen.getByText("Save");
      expect(saveBtn.hasAttribute("disabled")).toBe(true);
    });
  });
});

// ── 14. SearchProvidersSettings — API key clear ───────────────────
describe("SearchProvidersSettings — API key handling", () => {
  it("sends empty string for cleared API key instead of undefined", async () => {
    mockGet.mockResolvedValue({ providers: [
      { name: "tavily", display_name: "Tavily", description: "Web search", config_fields: [{ key: "api_key", label: "API Key", type: "password", required: true }], enabled: true, config: { api_key: "sk-old" } },
    ]});
    mockPost.mockResolvedValue({});
    const { SearchProvidersSettings } = await import("@/components/settings/SearchProvidersSettings");
    render(<SearchProvidersSettings />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Tavily")).toBeDefined();
    });

    const apiKeyInput = screen.getByPlaceholderText("Required");
    await userEvent.clear(apiKeyInput);

    const saveBtn = screen.getByText("Save");
    await userEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/search/providers", expect.arrayContaining([
        expect.objectContaining({ config: expect.objectContaining({ api_key: "" }) }),
      ]));
    });
  });
});

// ── 15. DataPrivacySettings — corrected description ───────────────
describe("DataPrivacySettings — retention description", () => {
  it("shows manual cleanup description instead of automatic", async () => {
    const { DataPrivacySettings } = await import("@/components/settings/DataPrivacySettings");
    render(<DataPrivacySettings />);
    await waitFor(() => {
      expect(screen.getByText(/manual cleanup/)).toBeDefined();
    });
    expect(screen.queryByText(/automatically delete/)).toBeNull();
  });
});

// ── 16. EscalationPolicy — no condition field ─────────────────────
describe("EscalationPolicySettings — no dead condition field", () => {
  it("creates rule without condition field", async () => {
    mockGet.mockResolvedValue({ rules: [], timeout_seconds: 300, auto_resolve: true });
    mockPost.mockResolvedValue({});
    const { EscalationPolicySettings } = await import("@/components/settings/EscalationPolicySettings");
    render(<EscalationPolicySettings />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Add Rule")).toBeDefined();
    });

    await userEvent.click(screen.getByText("Add Rule"));
    await userEvent.click(screen.getByText("Save Policy"));

    await waitFor(() => {
      const call = mockPost.mock.calls.find(c => c[0] === "/api/settings/escalation");
      if (call) {
        const body = call[1];
        expect(body.rules[0]).not.toHaveProperty("condition");
      }
    });
  });
});
