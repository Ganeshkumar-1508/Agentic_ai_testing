"use client";

import { cn } from "@/lib/utils";

// ─── Shimmer animation via CSS ───────────────────────────────────────────────

const shimmer = `
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}`;

// ─── Base skeleton block ─────────────────────────────────────────────────────

export function SkeletonBlock({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <>
      <style>{shimmer}</style>
      <div
        className={cn(
          "bg-white/[0.03] rounded-md relative overflow-hidden",
          "after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]",
          className
        )}
        {...props}
      />
    </>
  );
}

// ─── Dashboard Skeleton (4 stat cards + chart area) ──────────────────────────

export function DashboardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-6", className)}>
      {/* 4 stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="bg-surface border border-border rounded-xl p-6 space-y-4 shadow-card"
          >
            <SkeletonBlock className="w-10 h-10 rounded-lg" />
            <div className="space-y-2">
              <SkeletonBlock className="h-8 w-24" />
              <SkeletonBlock className="h-4 w-32" />
            </div>
          </div>
        ))}
      </div>

      {/* Chart area */}
      <div className="bg-surface border border-border rounded-xl p-6 shadow-card">
        <div className="space-y-3 mb-6">
          <SkeletonBlock className="h-6 w-48" />
          <SkeletonBlock className="h-4 w-64" />
        </div>
        <SkeletonBlock className="h-64 w-full rounded-lg" />
      </div>
    </div>
  );
}

// ─── Table Skeleton (header row + 5 body rows) ───────────────────────────────

export function TableSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-surface border border-border rounded-xl shadow-card overflow-hidden", className)}>
      {/* Header */}
      <div className="grid grid-cols-4 gap-4 p-4 border-b border-border">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonBlock key={i} className="h-4 w-24" />
        ))}
      </div>

      {/* 5 body rows */}
      {Array.from({ length: 5 }).map((_, row) => (
        <div
          key={row}
          className="grid grid-cols-4 gap-4 p-4 border-b border-border last:border-b-0"
        >
          {Array.from({ length: 4 }).map((_, col) => (
            <SkeletonBlock
              key={col}
              className={cn("h-4", col === 0 ? "w-40" : col === 1 ? "w-28" : col === 2 ? "w-20" : "w-16")}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

// ─── Agent Card Skeleton (individual agent card with progress bar placeholder) ──

export function AgentCardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-surface border border-border rounded-xl p-6 space-y-4 shadow-card", className)}>
      {/* Top row: avatar + name + badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SkeletonBlock className="w-10 h-10 rounded-lg" />
          <div className="space-y-2">
            <SkeletonBlock className="h-5 w-40" />
            <SkeletonBlock className="h-3 w-24" />
          </div>
        </div>
        <SkeletonBlock className="h-6 w-20 rounded-md" />
      </div>

      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex justify-between">
          <SkeletonBlock className="h-3 w-32" />
          <SkeletonBlock className="h-3 w-8" />
        </div>
        <SkeletonBlock className="h-2 w-full rounded-full" />
      </div>

      {/* Current task */}
      <SkeletonBlock className="h-4 w-3/4" />
    </div>
  );
}

// ─── Content Skeleton (generic lines of text) ────────────────────────────────

export function ContentSkeleton({
  lines = 6,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  const widths = ["full", "3/4", "5/6", "2/3", "4/5", "1/2"];
  return (
    <div className={cn("space-y-3", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonBlock
          key={i}
          className={cn(
            "h-4",
            i === 0 ? "w-1/3" : `w-${widths[(i - 1) % widths.length]}`
          )}
        />
      ))}
    </div>
  );
}
