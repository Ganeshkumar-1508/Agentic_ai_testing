"use client";

export interface StatusInfo {
  model: string;
  tokensUsed: number;
  costUsd: number;
  elapsedSeconds: number;
  currentTool?: string;
  agentStatus?: "idle" | "thinking" | "running_tool" | "generating";
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatElapsed(s: number): string {
  if (s < 60) return `${Math.floor(s)}s`;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}m ${sec.toString().padStart(2, "0")}s`;
}

export function StatusFooter({ info }: { info: StatusInfo }) {
  const burnRate = info.elapsedSeconds > 0
    ? (info.tokensUsed / info.elapsedSeconds)
    : 0;

  return (
    <div className="agent-status">
      <span className="agent-status-dot" data-status={info.agentStatus || "idle"} />
      {info.currentTool ? (
        <span className="agent-tool-indicator">running {info.currentTool}</span>
      ) : info.agentStatus === "thinking" ? (
        <span>thinking</span>
      ) : (
        <span>{info.model}</span>
      )}
      <span className="agent-status-sep">·</span>
      <span>{formatTokens(info.tokensUsed)} tok</span>
      <span className="agent-status-sep">·</span>
      <span>${info.costUsd.toFixed(4)}</span>
      <span className="agent-status-sep">·</span>
      <span>{formatElapsed(info.elapsedSeconds)}</span>
      {burnRate > 0 && (
        <>
          <span className="agent-status-sep">·</span>
          <span>{formatTokens(Math.round(burnRate))} tok/s</span>
        </>
      )}
    </div>
  );
}
