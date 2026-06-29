"use client";

import { useState, useEffect, useCallback } from "react";

export function useAutoRefresh(refetch: () => void, defaultInterval = 30_000) {
  const [enabled, setEnabled] = useState(false);
  const [interval, setIntervalMs] = useState(defaultInterval);

  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => refetch(), interval);
    return () => clearInterval(id);
  }, [enabled, interval, refetch]);

  const toggle = useCallback(() => setEnabled((p) => !p), []);

  return { autoRefresh: enabled, setAutoRefresh: setEnabled, toggle, interval, setIntervalMs } as const;
}
