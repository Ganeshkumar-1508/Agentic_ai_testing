import { describe, it, expect } from "vitest";
import {
  ACTIVITY_EVENT_TYPES,
  type ActivityEvent,
} from "@/lib/hooks/use-activity-feed";

/**
 * Tests for the activity feed hook's filter/normalization
 * logic. The actual SSE wiring is integration-only (jsdom
 * doesn't have a real EventSource), so we test the data
 * shape and the small helpers in the module.
 */

const ALL_TYPES = new Set<string>(ACTIVITY_EVENT_TYPES);

describe("ACTIVITY_EVENT_TYPES", () => {
  it("includes all 11 C01-C08 event types", () => {
    expect(ACTIVITY_EVENT_TYPES).toHaveLength(11);
    expect(ALL_TYPES.has("subagent.heartbeat")).toBe(true);
    expect(ALL_TYPES.has("subagent.spawned")).toBe(true);
    expect(ALL_TYPES.has("subagent.completed")).toBe(true);
    expect(ALL_TYPES.has("kg.refreshed")).toBe(true);
    expect(ALL_TYPES.has("kg.refreshed.failed")).toBe(true);
    expect(ALL_TYPES.has("board.completed")).toBe(true);
    expect(ALL_TYPES.has("board.failed")).toBe(true);
    expect(ALL_TYPES.has("team.created")).toBe(true);
    expect(ALL_TYPES.has("team.dissolved")).toBe(true);
    expect(ALL_TYPES.has("job.cancelled")).toBe(true);
    expect(ALL_TYPES.has("job.paused")).toBe(true);
  });

  it("uses the dotted naming convention", () => {
    for (const t of ACTIVITY_EVENT_TYPES) {
      expect(t).toMatch(/^[a-z]+(\.[a-z_]+)+$/);
    }
  });
});

describe("ActivityEvent shape", () => {
  it("supports the heartbeat payload", () => {
    const e: ActivityEvent = {
      id: "h1",
      type: "subagent.heartbeat",
      payload: {
        subagent_id: "sa-1",
        api_call_count: 3,
        current_tool: "code_search",
        stale_count: 0,
        elapsed_seconds: 12.4,
      },
      timestamp: "2026-06-21T00:00:00Z",
      receivedAt: 0,
    };
    expect(e.payload.current_tool).toBe("code_search");
  });

  it("supports the kg.refreshed payload", () => {
    const e: ActivityEvent = {
      id: "k1",
      type: "kg.refreshed",
      payload: {
        nodeCount: 1234,
        edgeCount: 5678,
        delta: { added: 10, removed: 2 },
        duration_ms: 42,
      },
      timestamp: "2026-06-21T00:00:01Z",
      receivedAt: 1,
    };
    expect(e.payload.delta).toEqual({ added: 10, removed: 2 });
  });
});
