// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusFooter, type StatusInfo } from "@/components/chat/StatusFooter";

function makeInfo(overrides: Partial<StatusInfo> = {}): StatusInfo {
  return {
    model: "test-model",
    tokensUsed: 1500,
    costUsd: 0.003,
    elapsedSeconds: 30,
    agentStatus: "generating",
    ...overrides,
  };
}

describe("StatusFooter", () => {
  it("renders model name", () => {
    render(<StatusFooter info={makeInfo()} />);
    expect(screen.getByText("test-model")).toBeDefined();
  });

  it("renders tokens with abbreviated format", () => {
    render(<StatusFooter info={makeInfo({ tokensUsed: 2500 })} />);
    expect(screen.getByText(/2\.5k/)).toBeDefined();
  });

  it("renders cost in USD", () => {
    render(<StatusFooter info={makeInfo({ costUsd: 0.0123 })} />);
    expect(screen.getByText("$0.0123")).toBeDefined();
  });

  it("renders elapsed time in seconds", () => {
    render(<StatusFooter info={makeInfo({ elapsedSeconds: 45 })} />);
    expect(screen.getByText("45s")).toBeDefined();
  });

  it("renders elapsed time in minutes", () => {
    render(<StatusFooter info={makeInfo({ elapsedSeconds: 125 })} />);
    expect(screen.getByText("2m 05s")).toBeDefined();
  });

  it("shows running tool name when currentTool is set", () => {
    render(<StatusFooter info={makeInfo({ currentTool: "bash", agentStatus: "running_tool" })} />);
    expect(screen.getByText(/running bash/)).toBeDefined();
  });

  it("shows thinking status when agent is thinking", () => {
    render(<StatusFooter info={makeInfo({ currentTool: "", agentStatus: "thinking" })} />);
    expect(screen.getByText("thinking")).toBeDefined();
  });

  it("shows token burn rate when elapsed > 0", () => {
    render(<StatusFooter info={makeInfo({ tokensUsed: 3000, elapsedSeconds: 60 })} />);
    expect(screen.getByText(/50 tok\/s/)).toBeDefined();
  });

  it("computes burn rate correctly for fractional tokens", () => {
    render(<StatusFooter info={makeInfo({ tokensUsed: 100, elapsedSeconds: 4 })} />);
    expect(screen.getByText(/25 tok\/s/)).toBeDefined();
  });

  it("does not show burn rate at 0 elapsed", () => {
    render(<StatusFooter info={makeInfo({ tokensUsed: 100, elapsedSeconds: 0 })} />);
    expect(screen.queryByText(/tok\/s/)).toBeNull();
  });

  it("high burn rate uses abbreviated format", () => {
    render(<StatusFooter info={makeInfo({ tokensUsed: 50000, elapsedSeconds: 10 })} />);
    expect(screen.getByText((content) => content.includes("5.0k") && content.includes("tok/s"))).toBeDefined();
  });
});
