"use client";

import { ChevronRight, AlertCircle, Wrench, FileText, Search, Image, Video, Music } from "lucide-react";
import { useState, type ReactNode } from "react";

export type ToolStatus = "running" | "done" | "error" | "idle";

export function ReasoningBlock({ steps }: { steps: string[] }) {
  const numbered = steps.map((s, i) => `${i + 1}. ${s}`).join("\n");
  return (
    <details className="agent-reasoning" open>
      <summary>
        <ChevronRight width={11} height={11} strokeWidth={2.5} />
        <span>Reasoning · {steps.length} steps</span>
      </summary>
      <pre>{numbered}</pre>
    </details>
  );
}

export function ToolCard({
  name,
  status,
  durationMs,
  body,
}: {
  name: string;
  status: ToolStatus;
  durationMs?: number;
  body?: string;
}) {
  const icon = name === "read_file" ? <FileText width={12} height={12} strokeWidth={2} />
            : name === "search_codebase" ? <Search width={12} height={12} strokeWidth={2} />
            : <Wrench width={12} height={12} strokeWidth={2} />;
  const ms = durationMs != null ? `${durationMs}ms` : status;
  return (
    <div className="agent-tool">
      <div className="agent-tool-head" data-status={status}>
        <span className="dot" />
        {icon}
        <span className="name">{name}</span>
        <span className="ms">{ms}</span>
      </div>
      {body && <div className="agent-tool-body">{body}</div>}
    </div>
  );
}

export function ApprovalCard({
  command,
  reason,
  onApprove,
  onDeny,
  busy,
}: {
  command: string;
  reason?: string;
  onApprove: (scope?: "once" | "session" | "always") => void;
  onDeny: () => void;
  busy?: boolean;
}) {
  const [expandScope, setExpandScope] = useState(false);
  return (
    <div className="agent-approval">
      <div className="agent-approval-head">
        <AlertCircle width={12} height={12} strokeWidth={2} />
        <span>Approval required</span>
      </div>
      <div className="agent-approval-msg">
        <code>{command}</code>
        {reason && <span className="agent-approval-reason">{reason}</span>}
      </div>
      {!expandScope ? (
        <div className="agent-approval-actions">
          <button type="button" className="allow" onClick={() => onApprove("once")} disabled={busy}>
            Allow
          </button>
          <button type="button" onClick={() => setExpandScope(true)} disabled={busy}>
            Allow options
          </button>
          <button type="button" className="deny" onClick={onDeny} disabled={busy}>
            Deny
          </button>
        </div>
      ) : (
        <div className="agent-approval-scope">
          <button type="button" className="allow" onClick={() => onApprove("once")} disabled={busy}>
            Allow once
          </button>
          <button type="button" className="allow-session" onClick={() => onApprove("session")} disabled={busy}>
            Allow for session
          </button>
          <button type="button" className="allow-always" onClick={() => onApprove("always")} disabled={busy}>
            Always allow
          </button>
          <button type="button" className="deny" onClick={onDeny} disabled={busy}>
            Deny
          </button>
          <button type="button" className="back" onClick={() => setExpandScope(false)} disabled={busy}>
            Back
          </button>
        </div>
      )}
    </div>
  );
}

export interface ChatMessageData {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  reasoning?: string[];
  tool?: { name: string; status: ToolStatus; durationMs?: number; body?: string };
  approval?: { id: string; command: string; reason?: string };
  timestamp: number;
  status?: "sending" | "sent" | "error";
  media?: { type: "image" | "video" | "audio"; url: string; alt?: string }[];
}

const IMG_RE = /!\[([^\]]*)\]\(([^)]+)\)/g;
const URL_RE = /(https?:\/\/[^\s]+(\.png|\.jpg|\.jpeg|\.gif|\.webp|\.svg)(\?[^\s]*)?)/gi;
const VIDEO_RE = /(https?:\/\/[^\s]+(\.mp4|\.webm|\.mov)(\?[^\s]*)?)/gi;
const AUDIO_RE = /(https?:\/\/[^\s]+(\.mp3|\.wav|\.ogg|\.m4a)(\?[^\s]*)?)/gi;

function renderContent(text: string, media?: ChatMessageData["media"]): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIdx = 0;
  let match: RegExpExecArray | null;

  // Check for explicit media attachments first
  if (media?.length) {
    for (const m of media) {
      if (m.type === "image") {
        nodes.push(<img key={`media-${nodes.length}`} src={m.url} alt={m.alt || ""} className="rounded-xl max-w-full max-h-96 my-2 border border-zinc-800/30" loading="lazy" />);
      } else if (m.type === "video") {
        nodes.push(<video key={`media-${nodes.length}`} src={m.url} controls className="rounded-xl max-w-full max-h-96 my-2 border border-zinc-800/30" />);
      } else if (m.type === "audio") {
        nodes.push(<audio key={`media-${nodes.length}`} src={m.url} controls className="my-2 w-full" />);
      }
    }
  }

  // Parse markdown images ![alt](url)
  IMG_RE.lastIndex = 0;
  match = IMG_RE.exec(text);
  while (match !== null) {
    if (match.index > lastIdx) nodes.push(<span key={`t-${lastIdx}`}>{text.slice(lastIdx, match.index)}</span>);
    nodes.push(<img key={`img-${nodes.length}`} src={match[2]} alt={match[1]} className="rounded-xl max-w-full max-h-96 my-2 border border-zinc-800/30" loading="lazy" />);
    lastIdx = IMG_RE.lastIndex;
    match = IMG_RE.exec(text);
  }

  // Check for standalone video URLs
  VIDEO_RE.lastIndex = 0;
  match = VIDEO_RE.exec(text);
  while (match !== null) {
    if (match.index > lastIdx) nodes.push(<span key={`t-${lastIdx}`}>{text.slice(lastIdx, match.index)}</span>);
    nodes.push(<video key={`vid-${nodes.length}`} src={match[0]} controls className="rounded-xl max-w-full max-h-96 my-2 border border-zinc-800/30" />);
    lastIdx = VIDEO_RE.lastIndex;
    match = VIDEO_RE.exec(text);
  }

  // Check for standalone audio URLs
  AUDIO_RE.lastIndex = 0;
  match = AUDIO_RE.exec(text);
  while (match !== null) {
    if (match.index > lastIdx) nodes.push(<span key={`t-${lastIdx}`}>{text.slice(lastIdx, match.index)}</span>);
    nodes.push(<audio key={`aud-${nodes.length}`} src={match[0]} controls className="my-2 w-full" />);
    lastIdx = AUDIO_RE.lastIndex;
    match = AUDIO_RE.exec(text);
  }

  // Check for standalone image URLs
  URL_RE.lastIndex = 0;
  match = URL_RE.exec(text);
  while (match !== null) {
    if (match.index > lastIdx) nodes.push(<span key={`t-${lastIdx}`}>{text.slice(lastIdx, match.index)}</span>);
    nodes.push(<img key={`url-img-${nodes.length}`} src={match[0]} alt="" className="rounded-xl max-w-full max-h-96 my-2 border border-zinc-800/30" loading="lazy" />);
    lastIdx = URL_RE.lastIndex;
    match = URL_RE.exec(text);
  }

  // Remaining text with inline code
  if (lastIdx < text.length || nodes.length === 0) {
    const remaining = text.slice(lastIdx);
    const parts = remaining.split(/(`[^`]+`)/g);
    for (const p of parts) {
      if (p.startsWith("`") && p.endsWith("`")) {
        nodes.push(<code key={`code-${nodes.length}`}>{p.slice(1, -1)}</code>);
      } else if (p) {
        nodes.push(<span key={`t-${nodes.length}`}>{p}</span>);
      }
    }
  }

  return nodes;
}

export function MessageBubble({
  message,
  index,
  onApprove,
  onDeny,
  onReact,
  busy,
}: {
  message: ChatMessageData;
  index: number;
  onApprove?: (approvalId: string, scope?: "once" | "session" | "always") => void;
  onDeny?: (approvalId: string) => void;
  onReact?: (msgId: string, kind: "up" | "down" | "none") => void;
  busy?: boolean;
}) {
  const [reasoningOpen, setReasoningOpen] = useState(false);
  if (message.role === "tool") {
    return (
      <ToolCard
        name="tool_result"
        status="done"
        body={message.content}
      />
    );
  }
  const isUser = message.role === "user";
  const avatarChar = isUser ? "U" : "A";
  return (
    <div
      className="agent-msg"
      data-role={message.role}
      style={{ "--msg-i": index } as React.CSSProperties}
    >
      <div className="agent-avatar" data-role={message.role}>
        {avatarChar}
      </div>
      <div className="agent-bubble" data-role={message.role}>
        {message.reasoning && message.reasoning.length > 0 && (
          <details
            className="agent-reasoning"
            open={reasoningOpen}
            onToggle={(e) => setReasoningOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary>
              <ChevronRight width={11} height={11} strokeWidth={2.5} />
              <span>Reasoning · {message.reasoning.length} steps</span>
            </summary>
            <pre>{message.reasoning.map((s, i) => `${i + 1}. ${s}`).join("\n")}</pre>
          </details>
        )}
        <div className="agent-bubble-body">
          {renderContent(message.content, message.media)}
        </div>
        {message.tool && (
          <ToolCard
            name={message.tool.name}
            status={message.tool.status}
            durationMs={message.tool.durationMs}
            body={message.tool.body}
          />
        )}
        {message.approval && onApprove && onDeny && (
          <ApprovalCard
            command={message.approval.command}
            reason={message.approval.reason}
            onApprove={(scope) => onApprove(message.approval!.id, scope)}
            onDeny={() => onDeny(message.approval!.id)}
            busy={busy}
          />
        )}
        {!isUser && onReact && (
          <div className="agent-msg-meta">
            <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
            <span>·</span>
            <button
              type="button"
              onClick={() => onReact(message.id, "up")}
              style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", padding: 0, font: "inherit" }}
              aria-label="Thumbs up"
            >
              ↑
            </button>
            <button
              type="button"
              onClick={() => onReact(message.id, "down")}
              style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", padding: 0, font: "inherit" }}
              aria-label="Thumbs down"
            >
              ↓
            </button>
          </div>
        )}
        {isUser && (
          <div className="agent-msg-meta">
            <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
          </div>
        )}
      </div>
    </div>
  );
}
