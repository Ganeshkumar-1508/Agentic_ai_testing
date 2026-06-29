"use client";

import { useState, useRef, useEffect, useCallback, memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal as TerminalIcon, Link, Unlink, Trash2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, BACKEND_URL } from "@/lib/api/api-client";

// ── Terminal Output (isolated perpetual animation component) ──────────
const TerminalOutput = memo(function TerminalOutput({
  lines,
  autoScroll,
  onScroll,
  endRef,
}: {
  lines: string[];
  autoScroll: boolean;
  onScroll: (e: React.UIEvent<HTMLDivElement>) => void;
  endRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      className="flex-1 p-4 overflow-y-auto font-mono text-[12px] leading-[1.7] max-h-[560px]"
      onScroll={onScroll}
    >
      {lines.length === 0 && (
        <div className="flex items-center justify-center h-full">
          <div className="text-center space-y-1">
            <p className="text-zinc-600 text-xs">No output yet</p>
            <p className="text-zinc-700 text-[10px]">Type a command to begin</p>
          </div>
        </div>
      )}
      <AnimatePresence initial={false}>
        {lines.map((line, i) => (
          <motion.div
            key={`${i}-${line.slice(0, 20)}`}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="text-zinc-400 whitespace-pre-wrap break-all py-[1px]"
          >
            {line}
          </motion.div>
        ))}
      </AnimatePresence>
      <div ref={endRef} />
    </div>
  );
});

// ── Status Indicator ─────────────────────────────────────────────────
function StatusDot({ state }: { state: "connected" | "connecting" | "disconnected" }) {
  const colors = {
    connected: "bg-emerald-400",
    connecting: "bg-amber-400 animate-pulse",
    disconnected: "bg-zinc-600",
  };
  return <span className={cn("w-1.5 h-1.5 rounded-full", colors[state])} />;
}

// ── Main Terminal Page ───────────────────────────────────────────────
export default function TerminalPage() {
  const [lines, setLines] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState("default");
  const [connState, setConnState] = useState<"connected" | "connecting" | "disconnected">("disconnected");
  const endRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bufferRef = useRef<string>("");

  useEffect(() => {
    if (autoScroll) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, autoScroll]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAutoScroll(dist < 40);
  }, []);

  const pushLine = useCallback((line: string) => {
    setLines((prev) => [...prev, line]);
  }, []);

  // ── WebSocket PTY ────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setConnState("connecting");

    const wsUrl = `${BACKEND_URL.replace("http", "ws")}/api/sandbox/${encodeURIComponent(sessionId)}/pty`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setConnState("connected");
      pushLine(`Connected to sandbox ${sessionId}`);
      inputRef.current?.focus();
    };

    ws.onmessage = (event) => {
      const data = typeof event.data === "string"
        ? event.data
        : new TextDecoder().decode(event.data);
      bufferRef.current += data;
      const parts = bufferRef.current.split("\n");
      bufferRef.current = parts.pop() || "";
      const newLines = parts.filter(Boolean);
      if (newLines.length > 0) {
        setLines((prev) => [...prev, ...newLines]);
      }
    };

    ws.onclose = () => {
      setConnState("disconnected");
      pushLine("Disconnected");
    };

    ws.onerror = () => setConnState("disconnected");

    wsRef.current = ws;
  }, [sessionId, pushLine]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnState("disconnected");
  }, []);

  // ── Keystroke handling ───────────────────────────────────────────
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const keyMap: Record<string, string> = {
      Enter: "\r", Backspace: "\x7f", Tab: "\t",
      ArrowUp: "\x1b[A", ArrowDown: "\x1b[B",
      ArrowRight: "\x1b[C", ArrowLeft: "\x1b[D",
      Home: "\x1b[H", End: "\x1b[F",
    };

    if (e.key === "c" && e.ctrlKey) { e.preventDefault(); wsRef.current.send(new TextEncoder().encode("\x03")); return; }
    if (e.key === "d" && e.ctrlKey) { e.preventDefault(); wsRef.current.send(new TextEncoder().encode("\x04")); return; }
    if (e.key === "l" && e.ctrlKey) { e.preventDefault(); wsRef.current.send(new TextEncoder().encode("\x0c")); return; }

    if (keyMap[e.key]) {
      e.preventDefault();
      wsRef.current.send(new TextEncoder().encode(keyMap[e.key]));
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      wsRef.current.send(new TextEncoder().encode(e.key));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  const statusLabel = { connected: "live", connecting: "connecting", disconnected: "idle" }[connState];

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
            <TerminalIcon size={16} className="text-zinc-400" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-[18px] font-medium tracking-tight text-zinc-100">Terminal</h1>
            <p className="text-[11px] text-zinc-600 mt-0.5">
              Interactive PTY session
              <span className="mx-1.5 text-zinc-700">/</span>
              <span className="text-zinc-500">{statusLabel}</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 bg-zinc-900/60 border border-zinc-800/50 rounded-lg px-2 py-1">
            <StatusDot state={connState} />
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value || "default")}
              placeholder="session"
              className="w-20 bg-transparent text-[11px] font-mono text-zinc-400 placeholder-zinc-700 outline-none"
            />
          </div>
          {connState === "connected" ? (
            <button
              onClick={disconnect}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-lg bg-white/[0.04] text-zinc-500 hover:text-zinc-300 transition-all active:scale-[0.97]"
            >
              <Unlink size={10} strokeWidth={1.5} />
              Disconnect
            </button>
          ) : (
            <button
              onClick={connect}
              disabled={connState === "connecting"}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-lg bg-white/[0.04] text-zinc-500 hover:text-zinc-300 transition-all active:scale-[0.97]"
            >
              <Link size={10} strokeWidth={1.5} />
              Connect
            </button>
          )}
          <button
            onClick={() => { setLines([]); setAutoScroll(true); }}
            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-lg bg-white/[0.04] text-zinc-500 hover:text-zinc-300 transition-all active:scale-[0.97]"
          >
            <Trash2 size={10} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* Terminal Container */}
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 200, damping: 25 }}
      >
        <div className="bg-zinc-950 border border-white/[0.06] rounded-2xl overflow-hidden shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_20px_40px_-15px_rgba(0,0,0,0.3)]">
          {/* Title bar */}
          <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-900/80 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/40" />
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/40" />
              <span className="text-[10px] text-zinc-600 font-mono ml-2">bash</span>
            </div>
            <span className="text-[10px] text-zinc-700 font-mono">{sessionId}</span>
          </div>

          {/* Output */}
          <TerminalOutput
            lines={lines}
            autoScroll={autoScroll}
            onScroll={handleScroll}
            endRef={endRef}
          />

          {/* Input */}
          <div className="px-4 pb-3 border-t border-white/[0.04]">
            <input
              ref={inputRef}
              type="text"
              autoFocus
              onKeyDown={handleKeyDown}
              className="w-full bg-transparent outline-none text-zinc-300 text-[12px] font-mono caret-emerald-400"
              placeholder={connState === "connected" ? "Type here..." : "Connect to start"}
              disabled={connState !== "connected"}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
            />
          </div>
        </div>

        {/* Scroll anchor */}
        {!autoScroll && lines.length > 3 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex justify-center mt-3"
          >
            <button
              onClick={() => { setAutoScroll(true); endRef.current?.scrollIntoView({ behavior: "smooth" }); }}
              className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-400 bg-zinc-900/40 border border-white/[0.04] rounded-full px-3 py-1.5 transition-all active:scale-[0.97]"
            >
              <ChevronDown size={10} strokeWidth={1.5} />
              Latest
            </button>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
