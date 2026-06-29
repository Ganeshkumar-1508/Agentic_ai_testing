"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export const StyledSelect = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => {
  return (
    <div className="relative">
      <select
        ref={ref}
        className={cn(
          "w-full appearance-none bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 pr-8",
          "text-sm text-neutral-200 placeholder:text-neutral-600",
          "focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20",
          "hover:border-white/[0.12] transition-colors",
          "cursor-pointer",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <svg className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-500 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" /></svg>
    </div>
  );
});
StyledSelect.displayName = "StyledSelect";
