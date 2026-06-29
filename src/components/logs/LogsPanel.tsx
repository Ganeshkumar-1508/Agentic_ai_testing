"use client";

import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { SessionSidebar } from "./SessionSidebar";
import { EventStream } from "./EventStream";
import { DetailDrawer } from "./DetailDrawer";
import { api } from "@/lib/api/api-client";

const SESSION_LIMIT = 20;
const EVENT_LIMIT = 50;

interface Session {
  id: string; status: string; prompt: string;
  total_tokens: number; total_cost: number;
  event_count: number; created_at: string; updated_at: string;
}

interface FlowEvent {
  id: string; type: string; raw_type: string;
  agent_id: string; parent_id: string | null; depth: number;
  duration_ms: number | null; token_count: number | null;
  tool_name: string | null; content_preview: string | null;
  created_at: string | null; payload: any;
}

export function LogsPanel() {
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [sessionSearch, setSessionSearch] = useState("");
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [eventFilters, setEventFilters] = useState<string[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<FlowEvent | null>(null);
  const [liveTail, setLiveTail] = useState(false);
  const [sessionCursor, setSessionCursor] = useState<string | null>(null);
  const [eventCursor, setEventCursor] = useState<string | null>(null);

  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    isError: sessionsError,
    error: sessionsErrorObj,
  } = useQuery({
    queryKey: ["logs", "sessions", sessionSearch, sessionStatus, sessionCursor],
    queryFn: async () => {
      const params: Record<string, string> = { limit: String(SESSION_LIMIT) };
      if (sessionSearch) params.search = sessionSearch;
      if (sessionStatus) params.status = sessionStatus;
      if (sessionCursor) params.cursor = sessionCursor;
      return api.get<any>("/api/logs/sessions", params);
    },
    retry: 1,
    staleTime: 0,
    refetchOnMount: 'always',
  });

  const {
    data: eventsData,
    isLoading: eventsLoading,
    isError: eventsError,
  } = useQuery({
    queryKey: ["logs", "events", selectedSession, eventFilters.sort().join(","), eventCursor],
    queryFn: async () => {
      if (!selectedSession) return { data: [], has_more: false };
      const params: Record<string, string> = { limit: String(EVENT_LIMIT) };
      if (eventFilters.length) params.type = eventFilters.join(",");
      if (eventCursor) params.cursor = eventCursor;
      return api.get<any>(`/api/logs/sessions/${selectedSession}/events`, params);
    },
    enabled: !!selectedSession,
    retry: 1,
    staleTime: 0,
    refetchOnMount: 'always',
  });

  const sessions: Session[] = (sessionsData as any)?.data ?? [];
  const events: FlowEvent[] = (eventsData as any)?.data ?? [];
  const sessionsHasMore = (sessionsData as any)?.has_more ?? false;
  const eventsHasMore = (eventsData as any)?.has_more ?? false;

  const handleSessionSelect = useCallback((id: string) => {
    setSelectedSession(id);
    setEventCursor(null);
    setSelectedEvent(null);
  }, []);

  const handleEventSelect = useCallback((event: FlowEvent) => {
    setSelectedEvent(prev => prev?.id === event.id ? null : event);
  }, []);

  const handleLoadMoreSessions = useCallback(() => {
    const next = (sessionsData as any)?.next_cursor;
    if (next) setSessionCursor(next);
  }, [sessionsData]);

  const handleLoadMoreEvents = useCallback(() => {
    const next = (eventsData as any)?.next_cursor;
    if (next) setEventCursor(next);
  }, [eventsData]);

  const handleSearch = useCallback((val: string) => {
    setSessionSearch(val);
    setSessionCursor(null);
  }, []);

  const handleStatusFilter = useCallback((status: string | null) => {
    setSessionStatus(status);
    setSessionCursor(null);
  }, []);

  const handleEventFilter = useCallback((type: string) => {
    setEventFilters(prev =>
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    );
    setEventCursor(null);
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex gap-6 min-h-0" style={{ minHeight: "480px" }}>
        <SessionSidebar
          sessions={sessions}
          selectedSession={selectedSession}
          search={sessionSearch}
          statusFilter={sessionStatus}
          hasMore={sessionsHasMore}
          loading={sessionsLoading}
          error={sessionsError ? (sessionsErrorObj as any)?.message ?? "Failed to load sessions" : null}
          onSearch={handleSearch}
          onStatusFilter={handleStatusFilter}
          onSelect={handleSessionSelect}
          onLoadMore={handleLoadMoreSessions}
        />

        <EventStream
          events={events}
          selectedEventId={selectedEvent?.id ?? null}
          eventFilters={eventFilters}
          hasMore={eventsHasMore}
          loading={eventsLoading}
          apiError={eventsError}
          liveTail={liveTail}
          sessionId={selectedSession}
          onEventFilter={handleEventFilter}
          onEventSelect={handleEventSelect}
          onLoadMore={handleLoadMoreEvents}
          onToggleLive={() => setLiveTail(p => !p)}
        />

        <DetailDrawer
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      </div>
    </div>
  );
}
