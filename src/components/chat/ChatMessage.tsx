"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { User, Pen, Copy, Check, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer";
import { ReasoningBlock } from "@/components/shared/ReasoningBlock";
import { ToolCallCard } from "@/components/shared/ToolCallCard";
import { ApprovalCard } from "@/components/chat/ApprovalCard";

export type ChatMessageData = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  reasoning?: string;
  reasoning_open?: boolean;
  tool_name?: string;
  tool_status?: string;
  tool_duration_ms?: number;
  timestamp: number;
};

export function ChatMessage({ msg, onToggleReasoning, onResend, onDelete, onApprove, onDeny }: {
  msg: ChatMessageData; onToggleReasoning: (id: string) => void; onResend?: (text: string) => void;
  onDelete?: (id: string) => void; onApprove?: (id: string, scope?: string) => void; onDeny?: (id: string) => void;
}) {
  const isUser = msg.role === "user";
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(msg.content);

  const handleCopyMsg = useCallback(() => {
    const text = `${isUser ? "User" : "Assistant"}: ${msg.content}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  }, [msg.content, isUser]);

  const handleEditSave = useCallback(() => {
    if (editText.trim() && editText !== msg.content) {
      onResend?.(editText);
    }
    setEditing(false);
  }, [editText, msg.content, onResend]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={`flex items-start gap-3 group ${isUser ? "" : "ml-10 border-l-2 border-emerald-400/20 pl-4"}`}
    >
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-zinc-800/80 flex items-center justify-center shrink-0 mt-0.5">
          <User size={12} className="text-zinc-500" strokeWidth={1.5} />
        </div>
      )}
      <div className="min-w-0 pt-0.5 flex-1 relative">
        {!isUser && msg.reasoning && (
          <ReasoningBlock
            content={msg.reasoning}
            defaultOpen={msg.reasoning_open ?? false}
          />
        )}
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            {isUser && editing ? (
              <div className="space-y-2">
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  className="w-full bg-zinc-900/60 border border-zinc-800/50 rounded-lg px-3 py-2 text-sm text-zinc-300 font-mono outline-none focus:border-emerald-500/40 resize-none"
                  rows={3}
                />
                <div className="flex gap-2">
                  <button onClick={handleEditSave} className="text-[11px] px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.97]">
                    <Check size={11} strokeWidth={1.5} className="inline mr-1" />Save
                  </button>
                  <button onClick={() => setEditing(false)} className="text-[11px] px-2.5 py-1 rounded-lg bg-zinc-800/30 text-zinc-500 hover:text-zinc-300 transition-colors active:scale-[0.97]">
                    Cancel
                  </button>
                </div>
              </div>
            ) : msg.tool_status === "pending" && onApprove && onDeny ? (
              <ApprovalCard id={msg.id} tool={msg.tool_name || "unknown"} onApprove={onApprove} onDeny={onDeny} />
            ) : (
              msg.content && <MarkdownRenderer content={msg.content} />
            )}
            {!isUser && msg.tool_name && msg.tool_status !== "pending" && (
              <ToolCallCard name={msg.tool_name} status={(msg.tool_status as "running" | "completed" | "error" | "pending") || "completed"} durationMs={msg.tool_duration_ms} />
            )}
            <p className="text-[11px] text-zinc-600 mt-1.5 font-mono">
              {new Date(msg.timestamp).toLocaleTimeString()}
            </p>
          </div>
          <div className="flex flex-col gap-1 shrink-0">
            {isUser && !editing && (
              <button onClick={() => { setEditing(true); setEditText(msg.content); }}
                className="p-1 rounded-md text-zinc-700 hover:text-zinc-400 hover:bg-zinc-800/50 transition-all opacity-0 group-hover:opacity-100 active:scale-[0.97]"
                title="Edit message">
                <Pen size={11} strokeWidth={1.5} />
              </button>
            )}
            <button onClick={handleCopyMsg}
              className="p-1 rounded-md text-zinc-700 hover:text-zinc-400 hover:bg-zinc-800/50 transition-all opacity-0 group-hover:opacity-100 active:scale-[0.97]"
              title="Copy message">
              {copied ? <Check size={11} strokeWidth={1.5} className="text-emerald-400" /> : <Copy size={11} strokeWidth={1.5} />}
            </button>
            <button onClick={() => onDelete?.(msg.id)}
              className="p-1 rounded-md text-zinc-700 hover:text-red-400 hover:bg-red-500/10 transition-all opacity-0 group-hover:opacity-100 active:scale-[0.97]"
              title="Delete message">
              <Trash2 size={11} strokeWidth={1.5} />
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
