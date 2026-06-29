"use client";

import { useState, type ReactNode } from "react";
import { X, GitBranch, AlertTriangle } from "lucide-react";

export type RailTab = "session" | "model" | "cost" | "context" | "tools";

export interface RailTool {
  name: string;
  status: "running" | "done" | "pending" | "error";
  durationMs?: number;
}

export function RightRail({
  activeTab,
  onTabChange,
  onClose,
  sessionEyebrow,
  sessionTitle,
  sessionStatus,
  sessionStartedAt,
  tokenUsed,
  tokenBudget,
  model,
  cost,
  costBudget,
  links,
  tools,
  onEndSession,
}: {
  activeTab: RailTab;
  onTabChange: (t: RailTab) => void;
  onClose: () => void;
  sessionEyebrow?: string;
  sessionTitle?: string;
  sessionStatus?: "running" | "idle" | "completed" | "failed";
  sessionStartedAt?: string;
  tokenUsed?: number;
  tokenBudget?: number;
  model?: string;
  cost?: number;
  costBudget?: number;
  links?: { label: string; value: string; tall?: boolean }[];
  tools?: RailTool[];
  onEndSession?: () => void;
}) {
  const tabLabels: Record<RailTab, string> = {
    session: "Session",
    model: "Model",
    cost: "Cost",
    context: "Context",
    tools: "Tools",
  };
  const tokenPct = tokenBudget && tokenBudget > 0 ? Math.min(100, ((tokenUsed ?? 0) / tokenBudget) * 100) : 0;

  return (
    <aside className="agent-rail" role="complementary">
      <div className="agent-rail-head">
        <div className="agent-rail-tabs">
          {(Object.keys(tabLabels) as RailTab[]).map((t) => (
            <button
              key={t}
              type="button"
              className="agent-rail-tab"
              data-active={t === activeTab ? "true" : "false"}
              onClick={() => onTabChange(t)}
            >
              {tabLabels[t]}
            </button>
          ))}
        </div>
        <button type="button" className="agent-rail-close" onClick={onClose} aria-label="Close panel">
          <X width={14} height={14} strokeWidth={2} />
        </button>
      </div>

      <div className="agent-rail-body">
        {activeTab === "session" && (
          <>
            <div>
              {sessionEyebrow && <div className="agent-rail-eyebrow">{sessionEyebrow}</div>}
              {sessionTitle && <h3 className="agent-rail-h3">{sessionTitle}</h3>}
              <div className="agent-rail-meta-row" style={{ marginTop: 6 }}>
                {sessionStatus && sessionStatus === "running" && (
                  <span className="agent-meta-pill">
                    <span className="agent-meta-dot" />
                    running
                  </span>
                )}
                {sessionStatus === "completed" && <span className="agent-meta-pill" style={{ background: "rgba(255,255,255,0.06)", color: "var(--text-2)" }}>completed</span>}
                {sessionStatus === "failed" && <span className="agent-meta-pill" style={{ background: "rgba(248,113,113,0.10)", color: "var(--danger)" }}>failed</span>}
                {sessionStatus === "idle" && <span className="agent-meta-pill" style={{ background: "rgba(255,255,255,0.04)", color: "var(--text-3)" }}>idle</span>}
                {sessionStartedAt && <span style={{ color: "var(--text-3)", fontSize: 11 }}>started {sessionStartedAt}</span>}
              </div>
            </div>

            <div className="agent-rail-bento">
              <div className="agent-bento-cell" data-area="wide">
                <div className="agent-bento-label">tokens used</div>
                <div className="agent-bento-value">
                  {((tokenUsed ?? 0) / 1000).toFixed(1)}k <span className="agent-bento-unit">/ {((tokenBudget ?? 200000) / 1000).toFixed(0)}k</span>
                </div>
                <div className="agent-gauge">
                  <div className="agent-gauge-fill" style={{ "--pct": `${tokenPct}%` } as React.CSSProperties} />
                </div>
              </div>
              <div className="agent-bento-cell" data-area="n1">
                <div className="agent-bento-label">model</div>
                <div className="agent-bento-value">{model ?? "—"}</div>
              </div>
              <div className="agent-bento-cell" data-area="n2">
                <div className="agent-bento-label">cost</div>
                <div className="agent-bento-value">${(cost ?? 0).toFixed(2)}</div>
              </div>
            </div>

            {tools && tools.length > 0 && (
              <div>
                <div className="agent-rail-h4-row">
                  <div className="agent-rail-h4">Active tools</div>
                  <div className="agent-rail-h4" style={{ textTransform: "none", letterSpacing: 0, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{tools.length}</div>
                </div>
                <ul className="agent-tool-list">
                  {tools.map((t) => (
                    <li key={t.name} className="agent-tool-row" data-status={t.status}>
                      {t.status === "running" && <span className="pulse" />}
                      {t.status === "done" && (
                        <span className="check">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </span>
                      )}
                      {t.status === "pending" && <span style={{ width: 6, height: 6, borderRadius: "50%", border: "1px dashed var(--text-4)", flexShrink: 0, margin: 3 }} />}
                      <span className="name">{t.name}</span>
                      <span className="ms">{t.status === "pending" ? "queued" : `${t.durationMs ?? 0}ms`}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {links && links.length > 0 && (
              <div>
                <div className="agent-rail-h4-row">
                  <div className="agent-rail-h4">Links</div>
                </div>
                <div className="agent-rail-bento" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  {links.map((l, i) => (
                    <a
                      key={`${l.label}-${i}`}
                      className="agent-bento-cell"
                      data-area={l.tall ? "wide" : "n1"}
                      href="#"
                      onClick={(e) => e.preventDefault()}
                      style={{ textDecoration: "none", color: "inherit" }}
                    >
                      <div className="agent-bento-label">{l.label}</div>
                      <div className="agent-bento-value" style={{ fontSize: 12 }}>{l.value}</div>
                    </a>
                  ))}
                </div>
              </div>
            )}

            {onEndSession && (
              <button type="button" className="agent-meta-chip" style={{ color: "var(--text-3)" }} onClick={onEndSession}>
                <AlertTriangle width={12} height={12} strokeWidth={2} />
                End session
              </button>
            )}
          </>
        )}

        {activeTab === "model" && (
          <ModelTab model={model} />
        )}

        {activeTab === "cost" && (
          <CostTab cost={cost} costBudget={costBudget} tokenUsed={tokenUsed} tokenBudget={tokenBudget} />
        )}

        {activeTab === "context" && (
          <ContextTab />
        )}

        {activeTab === "tools" && (
          <ToolsTab tools={tools} />
        )}
      </div>
    </aside>
  );
}

function ModelTab({ model }: { model?: string }) {
  return (
    <div>
      <div className="agent-rail-eyebrow">active model</div>
      <h3 className="agent-rail-h3">{model ?? "—"}</h3>
      <p style={{ color: "var(--text-3)", fontSize: 12, marginTop: 8 }}>
        Switch model from the composer chip. Cost &amp; quality tradeoffs update per request.
      </p>
    </div>
  );
}

function CostTab({
  cost,
  costBudget,
  tokenUsed,
  tokenBudget,
}: {
  cost?: number;
  costBudget?: number;
  tokenUsed?: number;
  tokenBudget?: number;
}) {
  const costPct = costBudget && costBudget > 0 ? Math.min(100, ((cost ?? 0) / costBudget) * 100) : 0;
  const tokenPct = tokenBudget && tokenBudget > 0 ? Math.min(100, ((tokenUsed ?? 0) / tokenBudget) * 100) : 0;
  return (
    <>
      <div className="agent-bento-cell" data-area="wide" style={{ padding: 12 }}>
        <div className="agent-bento-label">cost this session</div>
        <div className="agent-bento-value" style={{ fontSize: 22 }}>
          ${(cost ?? 0).toFixed(4)} <span className="agent-bento-unit">/ ${(costBudget ?? 5).toFixed(2)}</span>
        </div>
        <div className="agent-gauge" style={{ marginTop: 8 }}>
          <div className="agent-gauge-fill" style={{ "--pct": `${costPct}%` } as React.CSSProperties} />
        </div>
      </div>
      <div>
        <div className="agent-rail-h4">tokens</div>
        <div className="agent-bento-cell" data-area="wide" style={{ padding: 12, marginTop: 4 }}>
          <div className="agent-bento-value" style={{ fontSize: 14 }}>
            {tokenUsed?.toLocaleString() ?? 0} <span className="agent-bento-unit">/ {tokenBudget?.toLocaleString() ?? 200000}</span>
          </div>
          <div className="agent-gauge" style={{ marginTop: 8 }}>
            <div className="agent-gauge-fill" style={{ "--pct": `${tokenPct}%` } as React.CSSProperties} />
          </div>
        </div>
      </div>
    </>
  );
}

function ContextTab() {
  return (
    <div>
      <div className="agent-rail-eyebrow">context window</div>
      <p style={{ color: "var(--text-3)", fontSize: 12, marginTop: 8 }}>
        Conversation context, tool outputs, and memory entries the agent currently sees.
      </p>
      <div style={{ marginTop: 12, padding: 10, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
        No context inspector wired yet
      </div>
    </div>
  );
}

function ToolsTab({ tools }: { tools?: RailTool[] }) {
  if (!tools || tools.length === 0) {
    return (
      <div>
        <div className="agent-rail-eyebrow">tools</div>
        <p style={{ color: "var(--text-3)", fontSize: 12, marginTop: 8 }}>No tools active in this session yet.</p>
      </div>
    );
  }
  return (
    <ul className="agent-tool-list">
      {tools.map((t) => (
        <li key={t.name} className="agent-tool-row" data-status={t.status}>
          {t.status === "running" && <span className="pulse" />}
          {t.status === "done" && (
            <span className="check">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
          )}
          <span className="name">{t.name}</span>
          <span className="ms">{t.durationMs ?? 0}ms</span>
        </li>
      ))}
    </ul>
  );
}
