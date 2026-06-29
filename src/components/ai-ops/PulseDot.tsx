"use client";

export function PulseDot({ color = "bg-emerald-400", className = "" }: { color?: string; className?: string }) {
  return (
    <span className={`relative inline-flex ${className}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
      <span className={`absolute inset-0 w-1.5 h-1.5 rounded-full ${color} animate-ping opacity-30`} />
    </span>
  );
}
