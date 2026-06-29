"use client";

import { Plus, Search } from "lucide-react";

export type SessionStatus = "active" | "running" | "failed" | "completed" | "idle";

export interface SessionItem {
  id: string;
  title: string;
  status: SessionStatus;
  meta?: string;
  updatedAt?: string;
}

export function SessionRow({
  session,
  active,
  onClick,
}: {
  session: SessionItem;
  active: boolean;
  onClick: (id: string) => void;
}) {
  return (
    <button
      type="button"
      className="agent-session-row"
      data-status={session.status}
      data-active={active ? "true" : "false"}
      onClick={() => onClick(session.id)}
    >
      <span className="agent-session-dot" />
      <div className="agent-session-body">
        <div className="agent-session-title">{session.title}</div>
        {session.meta && <div className="agent-session-meta">{session.meta}</div>}
      </div>
    </button>
  );
}

export function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onNewChat,
  onSearch,
  searchValue,
  total,
}: {
  sessions: SessionItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onSearch?: (q: string) => void;
  searchValue?: string;
  total?: number;
}) {
  return (
    <aside className="agent-sidebar">
      <div className="agent-sidebar-head">
        <button type="button" className="agent-new-chat-btn" onClick={onNewChat}>
          <Plus width={13} height={13} strokeWidth={2} />
          <span>New chat</span>
          <span className="agent-kbd">⌘N</span>
        </button>
      </div>

      <div className="agent-sidebar-search">
        <Search width={12} height={12} strokeWidth={2} />
        <input
          type="text"
          placeholder="Search sessions"
          value={searchValue ?? ""}
          onChange={(e) => onSearch?.(e.target.value)}
        />
      </div>

      <div className="agent-session-list">
        {sessions.length === 0 ? (
          <div style={{ padding: "12px 8px", fontSize: 11, color: "var(--text-4)", textAlign: "center" }}>
            No sessions yet
          </div>
        ) : (
          sessions.map((s) => (
            <SessionRow key={s.id} session={s} active={s.id === activeId} onClick={onSelect} />
          ))
        )}
      </div>

      <div className="agent-sidebar-foot">
        <span>{total ?? sessions.length} sessions</span>
        <span>⌘B collapse</span>
      </div>
    </aside>
  );
}
