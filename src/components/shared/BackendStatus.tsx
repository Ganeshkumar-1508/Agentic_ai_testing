"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api/api-client";

export function BackendStatus() {
  const [status, setStatus] = useState<"checking" | "connected" | "disconnected">("checking");

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const res = await apiFetch("/health");
        if (mounted) setStatus(res.ok ? "connected" : "disconnected");
      } catch {
        if (mounted) setStatus("disconnected");
      }
    };
    check();
    const interval = setInterval(check, 15000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return (
    <div className="px-4 py-3 border-t border-border">
      <div className="flex items-center gap-2 text-xs">
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full",
            status === "connected" && "bg-emerald-400",
            status === "disconnected" && "bg-red-400",
            status === "checking" && "bg-amber-400 animate-pulse"
          )}
        />
        <span className="text-muted-foreground">
          {status === "connected" ? "Backend Connected" : status === "disconnected" ? "Backend Disconnected" : "Checking..."}
        </span>
      </div>
    </div>
  );
}
