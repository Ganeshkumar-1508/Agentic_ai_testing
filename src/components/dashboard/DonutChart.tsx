"use client";

import { motion } from "framer-motion";
interface DonutChartProps {
  passed?: number;
  failed?: number;
  skipped?: number;
  loading?: boolean;
}

interface Segment {
  value: number;
  color: string;
  label: string;
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  const rad = (angle - 90) * (Math.PI / 180);
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

export function DonutChart({ passed = 0, failed = 0, skipped = 0, loading }: DonutChartProps) {
  const total = passed + failed + skipped;
  const passRate = total > 0 ? Math.round((passed / total) * 100) : 0;

  const segments: Segment[] = [
    { value: passed, color: "#34d399", label: "Passed" },
    { value: failed, color: "#f87171", label: "Failed" },
    { value: skipped, color: "#6b7280", label: "Skipped" },
  ].filter((s) => s.value > 0);

  const cx = 60;
  const cy = 60;
  const r = 46;
  const totalValue = segments.reduce((s, seg) => s + seg.value, 0);

  let currentAngle = 0;
  const paths = segments.map((seg) => {
    const sliceAngle = (seg.value / totalValue) * 360;
    const path = describeArc(cx, cy, r, currentAngle, currentAngle + sliceAngle);
    currentAngle += sliceAngle;
    return { ...seg, path };
  });

  if (loading) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="w-24 h-4 rounded-full shimmer-bg" />
        <div className="h-[180px] rounded-full shimmer-bg mx-auto w-[180px]" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-glow h-full flex flex-col"
    >
      <div className="card-label mb-3">Test Distribution</div>
      <div className="flex-1 min-h-0 flex items-center">
        {total === 0 ? (
          <div className="h-[180px] flex items-center justify-center text-neutral-500 text-sm w-full">No data yet.</div>
        ) : (
          <div className="flex items-center gap-6 w-full">
            <div className="relative w-[120px] h-[120px] shrink-0">
              <svg width="120" height="120" viewBox="0 0 120 120">
                <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
                {paths.map((seg, i) => (
                  <motion.path
                    key={seg.label}
                    d={seg.path}
                    fill="none"
                    stroke={seg.color}
                    strokeWidth="10"
                    strokeLinecap="round"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ delay: 0.2 + i * 0.1, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                  />
                ))}
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-lg font-semibold text-neutral-100 font-mono">{passRate}%</div>
                  <div className="text-[10px] text-neutral-500">pass rate</div>
                </div>
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-xs text-neutral-400 font-mono">{passed.toLocaleString()}</span>
                <span className="text-xs text-neutral-500">passed</span>
              </div>
              {failed > 0 && (
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-400" />
                  <span className="text-xs text-neutral-400 font-mono">{failed.toLocaleString()}</span>
                  <span className="text-xs text-neutral-500">failed</span>
                </div>
              )}
              {skipped > 0 && (
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-gray-500" />
                  <span className="text-xs text-neutral-400 font-mono">{skipped.toLocaleString()}</span>
                  <span className="text-xs text-neutral-500">skipped</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}