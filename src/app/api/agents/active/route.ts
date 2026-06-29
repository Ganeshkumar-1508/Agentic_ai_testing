import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/agents/active
 *
 * Proxies the backend `/api/ops/swarm/active` endpoint and reshapes the
 * payload for the Agents dashboard. Falls back to an empty payload
 * (with `unreachable: true`) if the backend is offline so the page
 * still renders.
 */

export const dynamic = "force-dynamic";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8001";

type BackendSubagent = {
  id: string;
  goal: string;
  depth: number;
  role: string;
  status: string;
  started_at: number;
  tool_count: number;
  interrupted?: boolean;
};

type BackendActiveSession = {
  id: string;
  status: string;
  total_tokens: number;
  total_cost: number;
  created_at: string | null;
} | null;

type BackendResponse = {
  subagents: BackendSubagent[];
  active_session: BackendActiveSession;
  tool_calls_total: number;
};

function transform(sub: BackendSubagent) {
  return {
    id: sub.id,
    name: sub.id,
    role: sub.role,
    depth: sub.depth,
    status: sub.status,
    goal: sub.goal,
    currentTask: sub.goal,
    toolCurrentlyInvoked: sub.tool_count > 0 ? "in flight" : "idle",
    skillCurrentlyInvoked: null as string | null,
    sandboxRuntime: "python-uvloop", // mixin-based Agent has no separate runtime
    runtimeContainerId: sub.id, // subagent session id == container for our model
    lastActivityTimestamp: sub.started_at
      ? new Date(sub.started_at * 1000).toISOString()
      : null,
    interrupted: Boolean(sub.interrupted),
  };
}

export async function GET(_request: NextRequest) {
  try {
    const upstream = await fetch(`${BACKEND_URL}/api/ops/swarm/active`, {
      cache: "no-store",
      // short timeout via AbortController so a wedged backend doesn't hang
      // the page
      signal: AbortSignal.timeout(5_000),
    });

    if (!upstream.ok) {
      return NextResponse.json(
        {
          unreachable: true,
          status: upstream.status,
          agents: [],
          activeSession: null,
          toolCallsTotal: 0,
          fetchedAt: new Date().toISOString(),
        },
        { status: 200 },
      );
    }

    const data = (await upstream.json()) as BackendResponse;

    return NextResponse.json({
      unreachable: false,
      agents: (data.subagents || []).map(transform),
      activeSession: data.active_session
        ? {
            id: data.active_session.id,
            status: data.active_session.status,
            totalTokens: data.active_session.total_tokens,
            totalCost: data.active_session.total_cost,
            createdAt: data.active_session.created_at,
          }
        : null,
      toolCallsTotal: data.tool_calls_total || 0,
      fetchedAt: new Date().toISOString(),
    });
  } catch (err) {
    return NextResponse.json(
      {
        unreachable: true,
        error: err instanceof Error ? err.message : "unknown",
        agents: [],
        activeSession: null,
        toolCallsTotal: 0,
        fetchedAt: new Date().toISOString(),
      },
      { status: 200 },
    );
  }
}
