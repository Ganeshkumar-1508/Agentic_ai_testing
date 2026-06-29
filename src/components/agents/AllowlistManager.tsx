"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Shield,
  Trash2,
  X,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api/api-client";

interface AllowlistManagerProps {
  onClose?: () => void;
}

export function AllowlistManager({ onClose }: AllowlistManagerProps) {
  const [patterns, setPatterns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAllowlist = useCallback(async () => {
    try {
      const data = await api.get<{ patterns?: string[] }>("/api/permissions/allowlist");
      setPatterns(data?.patterns || []);
    } catch {
      // Silently retry
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAllowlist();
  }, [fetchAllowlist]);

  const revokePattern = async (pattern: string) => {
    try {
      await api.delete(`/api/permissions/allowlist/${encodeURIComponent(pattern)}`);
      setPatterns((prev) => prev.filter((p) => p !== pattern));
    } catch {
      // Handle error
    }
  };

  const clearAll = async () => {
    if (!window.confirm("Clear all always-allowed patterns?")) return;
    try {
      await api.post("/api/permissions/allowlist/clear");
      setPatterns([]);
    } catch {
      // Handle error
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-200 p-6 text-center text-sm text-zinc-400">
        Loading...
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-200">
      <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-800">
          <Shield className="h-4 w-4 text-emerald-600" />
          <span>Always-Allowed Patterns</span>
          {patterns.length > 0 && (
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500">
              {patterns.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {patterns.length > 0 && (
            <button
              onClick={clearAll}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-600 transition-all hover:bg-red-50 active:scale-[0.98]"
            >
              <AlertTriangle className="h-3 w-3" />
              Clear All
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="rounded-md p-1 text-zinc-400 transition-all hover:bg-zinc-100"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className="p-4">
        {patterns.length === 0 ? (
          <p className="text-center text-sm text-zinc-400">
            No always-allowed patterns. Approve a tool with &quot;Always&quot; to add one.
          </p>
        ) : (
          <div className="space-y-1">
            {patterns.map((pattern) => (
              <div
                key={pattern}
                className="group flex items-center justify-between rounded-md px-3 py-2 text-sm transition-all hover:bg-zinc-50"
              >
                <code className="break-all font-mono text-xs text-zinc-700">
                  {pattern}
                </code>
                <button
                  onClick={() => revokePattern(pattern)}
                  className="shrink-0 rounded-md p-1 text-zinc-300 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                  title="Revoke this pattern"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
