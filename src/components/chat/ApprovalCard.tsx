"use client";

import { useState } from "react";
import { Shield, ShieldCheck, ThumbsUp, ThumbsDown } from "lucide-react";

export function ApprovalCard({ id, tool, onApprove, onDeny }: {
  id: string; tool: string; onApprove: (id: string, scope?: string) => void; onDeny: (id: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="border border-amber-500/30 bg-amber-500/5 rounded-[1rem] p-3 my-2">
      <div className="flex items-center gap-2 mb-2">
        <Shield className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.5} />
        <span className="text-xs font-medium text-amber-400">Approval Required</span>
      </div>
      <p className="text-[11px] text-zinc-400 mb-3">The agent wants to run: <code className="text-amber-300 font-mono">{tool}</code></p>
      <div className="flex flex-wrap items-center gap-1.5">
        <button onClick={() => { setBusy(true); onApprove(id, "once"); }}
          disabled={busy}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.97] disabled:opacity-40">
          <ThumbsUp size={10} strokeWidth={1.5} />Once
        </button>
        <button onClick={() => { setBusy(true); onApprove(id, "session"); }}
          disabled={busy}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors active:scale-[0.97] disabled:opacity-40">
          <ShieldCheck size={10} strokeWidth={1.5} />Session
        </button>
        <button onClick={() => { setBusy(true); onApprove(id, "always"); }}
          disabled={busy}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-zinc-500/10 text-zinc-400 hover:bg-zinc-500/20 transition-colors active:scale-[0.97] disabled:opacity-40">
          <ShieldCheck size={10} strokeWidth={1.5} />Always
        </button>
        <span className="text-zinc-700 text-[10px]">|</span>
        <button onClick={() => { setBusy(true); onDeny(id); }}
          disabled={busy}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors active:scale-[0.97] disabled:opacity-40">
          <ThumbsDown size={10} strokeWidth={1.5} />Deny
        </button>
      </div>
    </div>
  );
}
