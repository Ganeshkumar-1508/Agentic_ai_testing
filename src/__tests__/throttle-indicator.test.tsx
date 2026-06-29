// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThrottleIndicator, type ThrottleState } from "@/components/jobs/ThrottleIndicator";

const baseState: ThrottleState = {
  spent_usd: 0.5,
  soft_cap_usd: 1.5,
  hard_cap_usd: 5.0,
  throttle_step: 0,
  hitl_active: false,
  sequential_active: false,
  cheaper_model_active: false,
  pause_requested: false,
};

describe("ThrottleIndicator", () => {
  describe("compact variant", () => {
    it("renders 5 pips + spent/cap in a single row", () => {
      const { container } = render(
        <ThrottleIndicator state={baseState} compact />,
      );
      const pips = container.querySelectorAll("span[title]");
      expect(pips.length).toBe(5);
    });

    it("highlights the current step with emerald", () => {
      const { container } = render(
        <ThrottleIndicator
          state={{ ...baseState, throttle_step: 2 }}
          compact
        />,
      );
      const pips = Array.from(container.querySelectorAll("span[title]"));
      const current = pips[2];
      expect(current.className).toContain("emerald");
    });

    it("uses rose for pause-requested step", () => {
      const { container } = render(
        <ThrottleIndicator
          state={{
            ...baseState,
            throttle_step: 4,
            pause_requested: true,
          }}
          compact
        />,
      );
      const pips = Array.from(container.querySelectorAll("span[title]"));
      expect(pips[4].className).toContain("rose");
    });

    it("renders spent and cap in monospace", () => {
      render(<ThrottleIndicator state={baseState} compact />);
      expect(screen.getByText(/\$0\.5/)).toBeDefined();
    });
  });

  describe("full variant", () => {
    it("renders the throttle title and 5 pips", () => {
      render(<ThrottleIndicator state={baseState} />);
      expect(screen.getByText("Budget throttle")).toBeDefined();
      expect(screen.getByText("Step 0")).toBeDefined();
      expect(screen.getByText("OK")).toBeDefined();
    });

    it("shows the current step number prominently", () => {
      render(<ThrottleIndicator state={{ ...baseState, throttle_step: 3 }} />);
      expect(screen.getByText("Step 3")).toBeDefined();
      expect(screen.getByText("Cheaper model")).toBeDefined();
    });

    it("renders the soft-cap percentage label", () => {
      render(
        <ThrottleIndicator
          state={{ ...baseState, spent_usd: 0.75 }}
        />,
      );
      expect(screen.getByText(/50% of soft cap/)).toBeDefined();
    });

    it("uses rose color for the spent figure when paused", () => {
      const { container } = render(
        <ThrottleIndicator
          state={{
            ...baseState,
            throttle_step: 4,
            pause_requested: true,
            spent_usd: 4.2,
          }}
        />,
      );
      const spentText = screen.getByText("$4.20");
      expect(spentText.className).toContain("rose");
    });

    it("uses amber color for the spent figure when warning", () => {
      render(
        <ThrottleIndicator
          state={{
            ...baseState,
            throttle_step: 1,
            hitl_active: true,
            spent_usd: 1.2,
          }}
        />,
      );
      const spentText = screen.getByText("$1.20");
      expect(spentText.className).toContain("amber");
    });
  });
});
