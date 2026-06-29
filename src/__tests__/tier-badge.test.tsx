// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TierBadge, TIER_LABEL } from "@/components/chat/TierBadge";

describe("TierBadge", () => {
  it("renders tier 1 label by default", () => {
    render(<TierBadge tier={1} />);
    expect(screen.getByText("Autonomous")).toBeDefined();
  });

  it("renders tier 2 label", () => {
    render(<TierBadge tier={2} />);
    expect(screen.getByText("Supervised")).toBeDefined();
  });

  it("renders tier 3 label", () => {
    render(<TierBadge tier={3} />);
    expect(screen.getByText("Human")).toBeDefined();
  });

  it("opens dropdown on click", async () => {
    render(<TierBadge tier={1} />);
    fireEvent.click(screen.getByTitle("Tier 1: Autonomous"));
    expect(screen.getByText("Autonomy Tier")).toBeDefined();
    expect(screen.getByText("Agent runs to completion autonomously")).toBeDefined();
  });

  it("calls onChange when selecting a different tier", () => {
    const onChange = vi.fn();
    render(<TierBadge tier={1} onChange={onChange} />);
    fireEvent.click(screen.getByTitle("Tier 1: Autonomous"));
    fireEvent.click(screen.getByText("Supervised"));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it("does not open dropdown when disabled", () => {
    render(<TierBadge tier={1} disabled />);
    fireEvent.click(screen.getByTitle("Tier 1: Autonomous"));
    expect(screen.queryByText("Autonomy Tier")).toBeNull();
  });

  it("shows correct description for each tier", () => {
    render(<TierBadge tier={1} />);
    fireEvent.click(screen.getByTitle("Tier 1: Autonomous"));

    expect(screen.getByText("Agent runs to completion autonomously")).toBeDefined();
    expect(screen.getByText("Agent pauses for human review before actions")).toBeDefined();
    expect(screen.getByText("Agent creates a proposal for human to execute")).toBeDefined();
  });

  it("TIER_LABEL has correct values", () => {
    expect(TIER_LABEL[1]).toBe("Autonomous");
    expect(TIER_LABEL[2]).toBe("Supervised");
    expect(TIER_LABEL[3]).toBe("Human");
  });
});
