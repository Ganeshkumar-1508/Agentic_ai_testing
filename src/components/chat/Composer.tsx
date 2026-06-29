"use client";

import { useEffect, useRef, useState, useCallback, type KeyboardEvent } from "react";
import { ChevronDown, FileText, Mic, Paperclip, Send, Square, Wrench, X } from "lucide-react";

export interface SlashCommand {
  cmd: string;
  desc: string;
  group?: "Commands" | "Files" | "Tools";
}

export interface AttachedFile {
  name: string;
  size?: number;
  mime?: string;
}

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  streaming,
  files,
  onRemoveFile,
  onAttach,
  onVoice,
  onModel,
  onTools,
  modelLabel,
  toolsCount,
  slashOpen,
  slashCommands,
  slashSelectedIdx,
  onSlashSelect,
  onSlashClose,
  dragOver,
  onDragOver,
  onDragLeave,
  onDrop,
  hint,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  streaming?: boolean;
  files?: AttachedFile[];
  onRemoveFile?: (idx: number) => void;
  onAttach?: () => void;
  onVoice?: () => void;
  onModel?: () => void;
  onTools?: () => void;
  modelLabel?: string;
  toolsCount?: number;
  slashOpen?: boolean;
  slashCommands?: SlashCommand[];
  slashSelectedIdx?: number;
  onSlashSelect?: (cmd: SlashCommand) => void;
  onSlashClose?: () => void;
  dragOver?: boolean;
  onDragOver?: (e: React.DragEvent) => void;
  onDragLeave?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
  hint?: React.ReactNode;
  busy?: boolean;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const adjustHeight = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 240) + "px";
  }, []);

  useEffect(adjustHeight, [draft, adjustHeight]);

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (slashOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        // move selection down
        const next = Math.min((slashSelectedIdx ?? 0) + 1, (slashCommands?.length ?? 1) - 1);
        onChange(draft);
        // Note: selection update should be handled by parent
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        return;
      }
      if (e.key === "Enter" && (slashCommands?.length ?? 0) > 0) {
        e.preventDefault();
        onSlashSelect?.(slashCommands![slashSelectedIdx ?? 0]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        onSlashClose?.();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (draft.trim().length > 0) onSubmit();
    }
  };

  return (
    <footer
      className="agent-composer"
      data-dragging={dragOver ? "true" : "false"}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver?.(e);
      }}
      onDragLeave={onDragLeave}
      onDrop={(e) => {
        e.preventDefault();
        onDrop?.(e);
      }}
    >
      {files && files.length > 0 && (
        <div className="agent-composer-chips">
          {files.map((f, i) => (
            <div className="agent-file-chip" key={`${f.name}-${i}`}>
              <FileText width={11} height={11} strokeWidth={2} />
              <span className="agent-file-name">{f.name}</span>
              {f.size != null && <span className="agent-file-size">{(f.size / 1024).toFixed(1)}k</span>}
              <button
                type="button"
                className="agent-chip-x"
                onClick={() => onRemoveFile?.(i)}
                aria-label={`Remove ${f.name}`}
              >
                <X width={10} height={10} strokeWidth={2.5} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="agent-composer-box">
        <textarea
          ref={taRef}
          rows={1}
          placeholder="Ask, search, or / for commands"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            onChange(e.target.value);
            adjustHeight();
          }}
          onKeyDown={handleKey}
          disabled={busy}
        />

        <div className="agent-composer-toolbar">
          <div className="agent-composer-left">
            {modelLabel !== undefined && (
              <button type="button" className="agent-meta-chip" onClick={onModel} disabled={busy}>
                <span className="agent-chip-icon">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M12 1v6m0 10v6M4.2 4.2l4.3 4.3m7 7l4.3 4.3M1 12h6m10 0h6M4.2 19.8l4.3-4.3m7-7l4.3-4.3" />
                  </svg>
                </span>
                <span>{modelLabel}</span>
                <ChevronDown className="agent-chev" width={9} height={9} strokeWidth={2.5} />
              </button>
            )}
            {toolsCount !== undefined && (
              <button type="button" className="agent-meta-chip" onClick={onTools} disabled={busy}>
                <span className="agent-chip-icon">
                  <Wrench width={11} height={11} strokeWidth={2} />
                </span>
                <span>
                  tools <span className="agent-chip-num">{toolsCount}</span>
                </span>
                <ChevronDown className="agent-chev" width={9} height={9} strokeWidth={2.5} />
              </button>
            )}
          </div>

          <div className="agent-composer-right">
            <button type="button" className="agent-icon-btn-sm" onClick={onAttach} disabled={busy} title="Attach file" aria-label="Attach file">
              <Paperclip width={13} height={13} strokeWidth={2} />
            </button>
            <button type="button" className="agent-icon-btn-sm" onClick={onVoice} disabled={busy} title="Voice input" aria-label="Voice input">
              <Mic width={13} height={13} strokeWidth={2} />
            </button>
            {streaming ? (
              <button type="button" className="agent-send-btn" data-streaming="true" onClick={onStop} aria-label="Stop generation">
                <Square width={12} height={12} fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                className="agent-send-btn"
                onClick={onSubmit}
                disabled={draft.trim().length === 0 || busy}
                aria-label="Send"
              >
                <Send width={14} height={14} strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>

        <div className="agent-composer-hint">
          {hint || (
            <>
              <span><kbd>⏎</kbd> send</span>
              <span><kbd>⇧</kbd><kbd>⏎</kbd> new line</span>
              <span><kbd>/</kbd> commands</span>
              <span className="agent-hint-spacer" />
              <span className="agent-hint-growl">ops · ready</span>
            </>
          )}
        </div>

        {slashOpen && slashCommands && slashCommands.length > 0 && (
          <div className="agent-slash-pop" role="listbox">
            {(["Commands", "Files", "Tools"] as const).map((group) => {
              const inGroup = slashCommands.filter((c) => (c.group ?? "Commands") === group);
              if (inGroup.length === 0) return null;
              return (
                <div key={group}>
                  <div className="agent-slash-section">{group}</div>
                  {inGroup.map((c) => {
                    const realIdx = slashCommands.indexOf(c);
                    return (
                      <button
                        key={c.cmd}
                        type="button"
                        className="agent-slash-item"
                        data-selected={realIdx === (slashSelectedIdx ?? 0) ? "true" : "false"}
                        onClick={() => onSlashSelect?.(c)}
                        role="option"
                      >
                        <span className="agent-slash-cmd">{c.cmd}</span>
                        <span className="agent-slash-desc">{c.desc}</span>
                      </button>
                    );
                  })}
                </div>
              );
            })}
            <div className="agent-slash-footer">
              <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
              <span><kbd>⏎</kbd> select</span>
              <span><kbd>esc</kbd> close</span>
            </div>
          </div>
        )}

        <div className="agent-drop-overlay" aria-hidden>
          <div className="agent-drop-inner">
            <div className="agent-drop-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div className="agent-drop-title">Drop to attach</div>
            <div className="agent-drop-sub">code · docs · images · up to 25MB</div>
          </div>
        </div>
      </div>
    </footer>
  );
}
