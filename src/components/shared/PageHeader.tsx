"use client";

import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title?: string;
  label?: string;
  route?: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  label,
  route,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("mb-8", className)}>
      <div className="flex items-start justify-between">
        <div>
          {route && (
            <div className="text-[10px] font-mono text-zinc-700 uppercase tracking-[0.1em] mb-1.5">{route}</div>
          )}
          <h1 className="text-[22px] font-medium tracking-tighter text-zinc-100 leading-none">
            {title}
          </h1>
          {label && (
            <div className="text-[11px] font-medium text-zinc-500 mt-1 uppercase tracking-[0.05em]">{label}</div>
          )}
          {description && (
            <p className="text-sm text-zinc-500 mt-1.5 max-w-2xl leading-relaxed">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-3 shrink-0 ml-6">{actions}</div>}
      </div>
    </div>
  );
}
