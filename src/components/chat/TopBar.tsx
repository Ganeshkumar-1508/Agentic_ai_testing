"use client";

import { Menu, PanelRight, Search, Settings2 } from "lucide-react";

interface TopBarProps {
  onToggleSidebar?: () => void;
  onToggleRail?: () => void;
  onOpenSearch?: () => void;
  onOpenSettings?: () => void;
  railOpen?: boolean;
  sidebarCollapsed?: boolean;
}

export function TopBar({
  onToggleSidebar,
  onToggleRail,
  onOpenSearch,
  onOpenSettings,
  railOpen,
  sidebarCollapsed,
}: TopBarProps) {
  return (
    <header className="agent-topbar">
      <div className="agent-brand">
        <div className="agent-brand-mark">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden>
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        <span>TestAI</span>
      </div>

      <div className="agent-topbar-actions">
        <button
          type="button"
          className="agent-search-trigger"
          onClick={onOpenSearch}
          aria-label="Open command palette"
        >
          <Search width={12} height={12} strokeWidth={2} />
          <span>Search sessions, tools, docs</span>
          <span className="agent-kbd">⌘K</span>
        </button>

        <button
          type="button"
          className="agent-icon-btn"
          onClick={onToggleSidebar}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label="Toggle sidebar"
        >
          <Menu width={14} height={14} strokeWidth={2} />
        </button>

        <button
          type="button"
          className="agent-icon-btn"
          onClick={onToggleRail}
          data-active={railOpen ? "true" : "false"}
          title="Toggle context panel"
          aria-label="Toggle context panel"
        >
          <PanelRight width={14} height={14} strokeWidth={2} />
        </button>

        <button
          type="button"
          className="agent-icon-btn"
          onClick={onOpenSettings}
          title="Settings"
          aria-label="Settings"
        >
          <Settings2 width={14} height={14} strokeWidth={2} />
        </button>
      </div>
    </header>
  );
}
