"use client";

import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface OverallProgressProps {
  progress: number;
  status: "idle" | "running" | "completed" | "failed";
}

export function OverallProgress({ progress, status }: OverallProgressProps) {
  const isRunning = status === "running";
  const isCompleted = status === "completed";

  if (!isRunning && !isCompleted) return null;

  return (
    <div className="flex items-center gap-4">
      {/* Bar container */}
      <div className="flex-1 h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
        <motion.div
          className={cn(
            "h-full rounded-full bg-emerald-500"
          )}
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{
            type: "spring",
            stiffness: 60,
            damping: 20,
          }}
        />
      </div>

      {/* Label */}
      <motion.div
        key={isCompleted ? "check" : "percent"}
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 15 }}
      >
        {isCompleted ? (
          <div className="flex items-center gap-1.5">
            <CheckCircle2
              className="w-4 h-4 text-emerald-400"
              strokeWidth={1.5}
            />
            <span className="text-xs font-mono text-emerald-400 tabular-nums">Complete</span>
          </div>
        ) : (
          <span className="text-xs font-mono text-muted-foreground min-w-[3ch] tabular-nums">
            {progress}%
          </span>
        )}
      </motion.div>
    </div>
  );
}
