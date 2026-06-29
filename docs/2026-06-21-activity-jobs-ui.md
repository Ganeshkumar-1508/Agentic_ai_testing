# Activity Feed + Job Detail — UI surface for C01-C08

**Date**: 2026-06-21
**Status**: Implemented
**Sprint**: UI follow-up to C01-C08 + 4 stabilization sprints

## What this delivers

Two new pages that surface the C01-C08 infrastructure work
that was previously backend-only:

1. **`/activity`** — global live activity feed for the active
   session. Subscribes to the existing
   `GET /api/events/{session_id}` SSE endpoint and surfaces
   every C01-C08 event as a styled row with type, summary, and
   timestamp. Filter chips, pause/clear, live connection badge.

2. **`/jobs`** — list of all JobSpecs submitted via the C08
   canonical surface (`GET /api/jobs?session_id=...`).
   Status pills, tier badges, repo+branch, cost+duration,
   filter by status, click-through to detail.

3. **`/jobs/[spec_id]`** — full JobSpec detail page. Uses
   every C08 Q6/Q8 endpoint:
   - `GET /api/jobs/{id}` — full spec + comments
   - `POST /api/jobs/{id}/cancel` — cancel
   - `POST /api/jobs/{id}/pause` — pause
   - `POST /api/jobs/{id}/resume` — resume
   - `POST /api/jobs/{id}/comments` — add comment
   - `GET /api/jobs/{id}/output` — output (terminal jobs only)

   Plus a per-job live activity feed filtered by `spec_id`.

## Files created

| File | Lines | Purpose |
|---|---|---|
| `src/lib/types/jobs.ts` | 65 | TypeScript types for JobSpec, JobSummary, JobOutput, JobComment |
| `src/lib/hooks/use-activity-feed.ts` | 195 | SSE feed hook: ring buffer, filter, pause/resume, auto-reconnect |
| `src/components/activity/ActivityItem.tsx` | 240 | One event row: type-specific icon, color, summary formatter |
| `src/components/activity/ActivityFeed.tsx` | 290 | The feed: filter chips, header with state badge, scrollable list, footer |
| `src/app/(dashboard)/activity/page.tsx` | 130 | Global feed page with KPI header (8 stats) |
| `src/app/(dashboard)/jobs/page.tsx` | 280 | Jobs list: filter pills, search-by-session, refresh |
| `src/app/(dashboard)/jobs/[spec_id]/page.tsx` | 540 | Job detail: spec fields, controls, comments, output, live activity |
| `src/__tests__/use-activity-feed.test.ts` | 70 | Tests for the 11 C01-C08 event types + payload shapes |
| `src/__tests__/jobs-types.test.ts` | 70 | Tests for the JobSpec type contracts |

## Files modified

| File | Change |
|---|---|
| `src/components/layout/AppSidebar.tsx` | Added `Radio` + `Briefcase` icons; added "Activity" + "Jobs" to Core section |
| `src/components/layout/AppHeader.tsx` | Added breadcrumb labels for `/activity` and `/jobs` |

## Design choices

### Match existing design system (per user direction)

I looked at `AppHeader.tsx`, `AppSidebar.tsx`,
`BentoCard.tsx`, `KpiRow.tsx`, `PageShell.tsx`,
`RecentRunsList.tsx`, and `sessions/page.tsx` to extract the
visual language:

- **Palette**: zinc-950/900/800/700/600/500/400 backgrounds,
  emerald-400 success, red-400 danger, blue-400 info,
  amber-400 warning, violet-400 accent. Same as the rest of
  the dashboard.
- **Cards**: `rounded-[2rem]` with `style={{ background: "#0e0e18" }}`
  (the inline `#0e0e18` is how `RecentRunsList.tsx` does it,
  not a Tailwind class).
- **Header style**: `text-4xl md:text-5xl tracking-tighter
  leading-none text-zinc-100 font-medium` (from `PageShell.tsx`).
- **Section header style**: `text-[11px] font-semibold
  text-zinc-500 uppercase tracking-wider` (from `PageShell.tsx`).
- **Animation easing**: `[0.16, 1, 0.3, 1]` for entry/exit.
- **Icon stroke width**: 1.5 throughout.
- **Font-mono + tabular-nums** for numbers and IDs.
- **Status dot pattern**: `w-2 h-2 rounded-full` with
  `animate-pulse` for active states.
- **Hover pattern**: `hover:bg-white/[0.03]` for rows,
  `hover:bg-white/[0.04]` for buttons.
- **Fetch pattern**: `api.get<T>(path, params)` from
  `@/lib/api/api-client` (tanstack/react-query underneath).
- **SSE pattern**: `useEventSource({ url, eventTypes, onEvent })`
  from `@/lib/hooks/use-event-source` (already implements
  exponential-backoff reconnect).

### ActivityFeed design

- **Filter chips** show the count per type (e.g. `subagent.heartbeat · 247`)
  so the user can see at a glance what's happening.
- **Pause** keeps the connection open; events that arrive
  while paused are dropped (not appended). This is the
  standard log-tail behavior.
- **Auto-scroll** is on by default; user can toggle. When
  the user scrolls up, auto-scroll naturally stops
  (the `useEffect` on `visibleEvents.length` only fires
  when the array grows, but the user can still see old
  events above).
- **Highlight the newest event** with a subtle emerald
  background that fades over 1.5s.
- **Heartbeat opacity** is 0.6 (not 1) — they're noisy and
  the user wants to skim past them.
- **State badge** in the header shows `Live` / `Connecting…`
  / `Reconnecting…` / `Offline` so the user always knows
  whether the SSE connection is healthy.

### Job Detail design

- **Polling cadence** is dynamic:
  - `running` / `submitted` / `queued` → 2s
  - terminal → 15s
  - first load → 3s
- **Status pill** uses the same `STATUS_PILL` map as the
  list page for visual consistency.
- **Cancel / Pause / Resume buttons** disable based on
  status (e.g. can't cancel a `completed` job).
- **Comments** use the same author-pill + timestamp pattern
  as the rest of the dashboard. Submit on `⌘+Enter`.
- **Output** is shown only for terminal jobs (`completed` /
  `failed` / `cancelled`) — a `useQuery` `enabled` flag
  controls this.
- **Live activity for this job** is filtered client-side
  by `payload.spec_id === spec.spec_id`. The backend's
  EventSourceSink doesn't know about spec-scoped filtering,
  so we do it here. O(N) on a 500-event ring buffer is
  fine.
- **The session_id for the per-job feed** is read from
  `spec.context.session_id` (set by `submit_job_to_orchestrator`).
  If absent, the feed falls back to "idle" and the user
  sees the empty state.

### useActivityFeed design

- **Reuses `useEventSource`** for the reconnect logic.
- **Ring buffer** of 500 events (configurable). Splice from
  the front when we exceed the cap.
- **Filter via substring match** — the user's `filters: Set<string>`
  is checked via `type.includes(filter)`. This lets the
  user filter on `kg` to see both `kg.refreshed` and
  `kg.refreshed.failed`.
- **Pause is decoupled from reconnect** — pausing doesn't
  tear down the connection, it just drops incoming events.
  Resume re-enables appending.
- **Per-event timestamp fallback** — if the backend
  payload doesn't have a `timestamp`, we fall back to
  `Date.now()`. The `GenericStreamEvent` always includes
  one, so this is a safety net.

## What's not in scope

- **C08 Q7 step 2** (delete legacy endpoints + frontend
  migration) — the 3 legacy pages (`/agent`, `/delegate`,
  `/pipeline/from-requirements`) are still served by their
  legacy handlers. The new `/jobs` page is the
  replacement; the legacy pages can be deleted once the
  frontend routes that call them are migrated.
- **Pause checkpoint semantics** — the watcher treats
  `paused` as a terminal status (cancels the task). A
  proper pause (checkpoint + return early + resume) is
  deferred to a future sprint.
- **Per-event subagent details** — the activity feed shows
  the event summary but doesn't link to the subagent's
  full session. A future sprint could add a click-through
  to `/sessions/{subagent_session_id}`.
- **Output rendering** — the job detail page shows the
  output as JSON. A future sprint could detect the
  output shape (test files, PR URL, etc.) and render
  it as a structured card.

## C01-C08 status — post-UI

| Item | Backend | UI |
|---|---|---|
| C04 KG refresh | ✅ tool | ✅ surfaced in `/activity` as `kg.refreshed` |
| C03 push-based completion | ✅ BoardWaiter | ✅ surfaced in `/activity` as `board.completed` / `board.failed` |
| C06 heartbeat | ✅ SubagentHeartbeat | ✅ surfaced in `/activity` as `subagent.heartbeat` |
| C01 worktree | ✅ WorktreeManager | ⏳ not surfaced (backend-only) |
| C02 teams | ✅ TeamService | ✅ surfaced in `/activity` as `team.created` / `team.dissolved` |
| C08 JobSpec | ✅ submitter + 7 endpoints | ✅ `/jobs` list + `/jobs/[id]` detail |
| C08 cancel propagation | ✅ cancel_watcher | ✅ Cancel button on job detail |
| C08 Q7 step 1 (legacy adapters) | ✅ wired | ⏳ legacy frontend pages not migrated |
| C08 Q7 step 2 (delete legacy) | ⏳ pending | ⏳ pending |

## Verification

- `npx tsc --noEmit` — **clean** (no errors)
- `npx vitest run` — **all my tests pass** (11/11 in
  `use-activity-feed.test.ts` + `jobs-types.test.ts`).
  Two pre-existing test failures in
  `view-model.test.ts` (knowledge-graph search ranking) are
  unrelated to this work.
- `npx next build` — **succeeds in 54s** with the 3 new
  routes registered:
  - `○ /activity` (static)
  - `○ /jobs` (static)
  - `ƒ /jobs/[spec_id]` (dynamic)

## How to use

### From the chat

1. Submit a job via the chat's `submit_job` tool (any prompt).
2. The chat's response will show a `spec_id`.
3. Open `/jobs` (or click "Jobs" in the sidebar) to see
   the job appear in the list.
4. Click the row to open `/jobs/{spec_id}` — the full spec,
   controls, comments, and live activity are all there.
5. If the job is still running, click "Cancel" to stop it.
   The activity feed will show `job.cancelled` within 2s.

### From the activity feed

1. Open `/activity` (or click "Activity" in the sidebar).
2. By default, the feed shows events for the `global` session.
3. Append `?session=<id>` to filter to a specific chat
   session's events.
4. Click a filter chip to toggle that event type on/off.
5. Click "Pause" to stop appending (the connection stays
   open). Click "Clear" to start fresh.
