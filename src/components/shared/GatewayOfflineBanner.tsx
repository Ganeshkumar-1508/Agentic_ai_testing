"use client";

import { useEffect, useRef, useState } from "react";
import { WifiOff, RefreshCw } from "lucide-react";

const RETRY_INTERVAL_MS = 10_000;

interface GatewayOfflineBannerProps {
  gatewayUnavailable: boolean;
}

function checkHealth(): Promise<boolean> {
  return fetch("/api/health", {
    credentials: "include",
    cache: "no-store",
  })
    .then((r) => r.ok)
    .catch(() => false);
}

export function GatewayOfflineBanner({ gatewayUnavailable }: GatewayOfflineBannerProps) {
  const [show, setShow] = useState(gatewayUnavailable);
  const probing = useRef(false);

  useEffect(() => {
    if (!gatewayUnavailable) {
      setShow(false);
      return;
    }
    setShow(true);

    const probe = async () => {
      if (probing.current) return;
      probing.current = true;
      const ok = await checkHealth();
      probing.current = false;
      if (ok) setShow(false);
    };

    const interval = window.setInterval(probe, RETRY_INTERVAL_MS);
    probe();
    return () => window.clearInterval(interval);
  }, [gatewayUnavailable]);

  if (!show) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-between gap-3 border-b border-amber-500/20 bg-amber-500/5 px-4 py-2 text-sm text-amber-400/80"
    >
      <span className="flex items-center gap-2">
        <WifiOff size={14} strokeWidth={1.5} />
        Gateway is unreachable. Retrying...
      </span>
      <button
        type="button"
        onClick={() => { setShow(false); }}
        className="flex items-center gap-1 rounded-md border border-zinc-800/50 px-2.5 py-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors active:scale-[0.97]"
      >
        <RefreshCw size={11} strokeWidth={1.5} />
        Dismiss
      </button>
    </div>
  );
}
