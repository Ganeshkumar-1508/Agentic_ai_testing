"use client";

import { Clock, Loader2, CheckCheck, XCircle, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type AgentStatus = "pending" | "running" | "completed" | "failed";

interface AgentBadgeProps {
  status: AgentStatus;
  size?: "sm" | "md";
  className?: string;
}

const statusConfig: Record<
  AgentStatus,
  {
    icon: LucideIcon;
    label: string;
    containerClass: string;
    iconClass: string;
  }
> = {
  pending: {
    icon: Clock,
    label: "Pending",
    containerClass: "border border-dashed border-neutral-600 bg-transparent",
    iconClass: "text-neutral-500",
  },
  running: {
    icon: Loader2,
    label: "Running",
    containerClass: "border border-solid border-emerald-500/30 bg-emerald-500/5",
    iconClass: "text-emerald-400",
  },
  completed: {
    icon: CheckCheck,
    label: "Completed",
    containerClass: "border border-solid border-emerald-500/30 bg-emerald-500/10",
    iconClass: "text-emerald-400",
  },
  failed: {
    icon: XCircle,
    label: "Failed",
    containerClass: "border border-solid border-red-500/30 bg-red-500/10",
    iconClass: "text-red-400",
  },
};

export function AgentBadge({ status, size = "md", className }: AgentBadgeProps) {
  const config = statusConfig[status];
  const Icon = config.icon;

  const sizeClasses = size === "sm" ? "gap-1 px-2 py-0.5 text-[10px]" : "gap-1.5 px-3 py-1 text-xs";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-medium",
        sizeClasses,
        config.containerClass,
        className
      )}
    >
      <Icon
        className={cn(
          size === "sm" ? "w-3 h-3" : "w-3.5 h-3.5",
          config.iconClass,
          status === "running" && "animate-spin"
        )}
        strokeWidth={1.5}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}
