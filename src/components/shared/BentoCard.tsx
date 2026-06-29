"use client";

import type { ReactNode, ElementType } from "react";
import { cn } from "@/lib/utils";

interface BentoCardProps {
  children: ReactNode;
  className?: string;
  icon?: ElementType;
  label?: string;
  description?: string;
  action?: ReactNode;
  elevated?: boolean;
  padding?: "sm" | "md" | "lg";
}

const paddings = {
  sm: "p-3",
  md: "p-5",
  lg: "p-8",
};

export function BentoCard({
  children,
  className,
  icon: Icon,
  label,
  description,
  action,
  elevated,
  padding = "md",
}: BentoCardProps) {
  return (
    <div
      className={cn(
        "bg-white/[0.03] p-1.5 rounded-3xl ring-1 ring-white/[0.06] transition-all duration-300",
        elevated && "shadow-[0_8px_32px_rgba(0,0,0,0.4)]",
        className,
      )}
    >
      <div className="bg-card rounded-[calc(2rem-0.375rem)] shadow-[inset_0_1px_1px_rgba(255,255,255,0.08)] h-full">
        {(label || Icon) && (
          <div className={cn("flex items-center justify-between", paddings[padding], "pb-0")}>
            <div className="flex items-center gap-3 min-w-0">
              {Icon && (
                <div className="w-8 h-8 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                </div>
              )}
              <div className="min-w-0">
                {label && (
                  <p className="text-sm font-medium text-neutral-200 tracking-tight truncate">
                    {label}
                  </p>
                )}
                {description && (
                  <p className="text-[11px] text-neutral-500 truncate">{description}</p>
                )}
              </div>
            </div>
            {action && <div className="shrink-0">{action}</div>}
          </div>
        )}
        <div className={cn(paddings[padding])}>{children}</div>
      </div>
    </div>
  );
}
