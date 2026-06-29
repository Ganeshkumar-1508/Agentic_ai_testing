"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface Analytics30dData {
  tests_run: number;
  pass_rate: number;
  flaky_rate: number;
  flaky_count: number;
  spark_tests: number[];
  spark_pass_rate: number[];
  spark_flaky: number[];
  change_tests_pct: number;
  change_pass_pct: number;
  change_flaky_pct: number;
  days: number;
  days_with_data: number;
}

function Sparkline({ values, color, max = 100 }: { values: number[]; color: string; max?: number }) {
  if (values.length === 0) {
    return <div className="h-7 flex-1 flex items-center justify-center text-[10px] text-neutral-700">—</div>;
  }
  const height = 28;
  const width = 100;
  const stepX = values.length > 1 ? width / (values.length - 1) : width;
  const maxVal = Math.max(max, ...values, 1);
  const points = values.map((v, i) => {
    const x = i * stepX;
    const y = height - (v / maxVal) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const linePath = `M ${points.join(" L ")}`;
  const lastPoint = points[points.length - 1]?.split(",") || ["0", "0"];
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-7 flex-1 overflow-visible">
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastPoint[0]} cy={lastPoint[1]} r="1.5" fill={color} />
    </svg>
  );
}

function MetricRow({
  label,
  value,
  unit,
  change,
  changeColor,
  values,
  color,
  isNegativeGood = false,
}: {
  label: string;
  value: string;
  unit?: string;
  change: number;
  changeColor: string;
  values: number[];
  color: string;
  isNegativeGood?: boolean;
}) {
  const isPositive = change > 0;
  const goodDirection = isNegativeGood ? !isPositive : isPositive;
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-3 py-2"
    >
      <div className="min-w-[90px]">
        <div className="text-[10px] text-neutral-500">{label}</div>
          <div className="text-lg font-semibold font-mono leading-tight" style={{ color }}>
          {value}
          {unit && <span className="text-[10px] text-neutral-500 ml-0.5">{unit}</span>}
        </div>
      </div>
      <Sparkline values={values} color={color} />
      <div className={cn("text-[10px] font-mono min-w-[42px] text-right", changeColor)}>
        {change === 0 ? "—" : `${isPositive ? "+" : ""}${change.toFixed(1)}%`}
      </div>
    </motion.div>
  );
}

export function Analytics30dCard() {
  const { data, isLoading } = useQuery<Analytics30dData>({
    queryKey: ["dashboard-analytics-30d"],
    queryFn: () => api.get<Analytics30dData>("/api/dashboard/widgets/analytics-30d"),
    refetchInterval: 60_000,
  });

  const hasData = (data?.days_with_data ?? 0) > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.9, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-3 shrink-0">
          <div className="card-label">30-Day Analytics</div>
        <div className="text-[10px] text-neutral-600">
          {data?.days_with_data ?? 0} days with data
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2 flex-1">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-12 rounded shimmer-bg" />
          ))}
        </div>
      ) : !hasData ? (
        <div className="text-xs text-neutral-600 text-center py-8 flex-1 flex items-center justify-center">No analytics data in the last 30 days.</div>
      ) : (
        <div className="divide-y divide-white/[0.04] flex-1 min-h-0">
          <MetricRow
            label="Tests Run"
            value={data?.tests_run.toLocaleString() ?? "0"}
            change={data?.change_tests_pct ?? 0}
            changeColor="text-emerald-400"
            values={data?.spark_tests ?? []}
            color="#34d399"
          />
          <MetricRow
            label="Pass Rate"
            value={`${data?.pass_rate.toFixed(1) ?? "0"}`}
            unit="%"
            change={data?.change_pass_pct ?? 0}
            changeColor="text-emerald-400"
            values={data?.spark_pass_rate ?? []}
            color="#34d399"
          />
          <MetricRow
            label="Flaky Rate"
            value={`${data?.flaky_rate.toFixed(1) ?? "0"}`}
            unit="%"
            change={data?.change_flaky_pct ?? 0}
            changeColor="text-amber-400"
            values={data?.spark_flaky ?? []}
            color="#f59e0b"
            isNegativeGood
          />
        </div>
      )}
    </motion.div>
  );
}
