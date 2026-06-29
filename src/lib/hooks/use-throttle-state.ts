"use client";

import { useMemo } from "react";
import {
  useActivityFeed,
  type ActivityEvent,
} from "@/lib/hooks/use-activity-feed";
import type { ThrottleState, ThrottleStep } from "@/components/jobs/ThrottleIndicator";

const DEFAULT_CONFIG = {
  soft_cap_usd: 1.5,
  hard_cap_usd: 5.0,
};

function asThrottleStep(value: unknown): ThrottleStep {
  const n = Number(value);
  if (n === 1 || n === 2 || n === 3 || n === 4) return n;
  return 0;
}

export interface UseThrottleStateOptions {
  sessionId: string | null;
  specId?: string;
  softCapUsd?: number;
  hardCapUsd?: number;
  maxEvents?: number;
}

export function useThrottleState({
  sessionId,
  specId,
  softCapUsd,
  hardCapUsd,
  maxEvents = 100,
}: UseThrottleStateOptions): ThrottleState {
  const { events } = useActivityFeed({
    sessionId,
    filters: new Set(["budget.throttled"]),
    maxEvents,
  });
  return useMemo<ThrottleState>(() => {
    const soft = softCapUsd ?? DEFAULT_CONFIG.soft_cap_usd;
    const hard = hardCapUsd ?? DEFAULT_CONFIG.hard_cap_usd;
    let step: ThrottleStep = 0;
    let spent = 0;
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i];
      if (ev.type !== "budget.throttled") continue;
      if (specId) {
        const evSpec = ev.payload?.spec_id;
        if (typeof evSpec === "string" && evSpec !== specId) continue;
      }
      const payload = ev.payload || {};
      step = asThrottleStep(payload.new_step);
      const s = Number(payload.spent_usd);
      if (Number.isFinite(s) && s > spent) spent = s;
      break;
    }
    return {
      spent_usd: spent,
      soft_cap_usd: soft,
      hard_cap_usd: hard,
      throttle_step: step,
      hitl_active: step >= 1,
      sequential_active: step >= 2,
      cheaper_model_active: step >= 3,
      pause_requested: step >= 4,
    };
  }, [events, specId, softCapUsd, hardCapUsd]);
}
