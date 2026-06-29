"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { PhaseName, PhaseState } from "@/lib/types/pipeline";
import { AlertTriangle, GitFork, CheckCircle, XCircle, SkipForward } from "lucide-react";

interface PipelineDagProps {
  phases: PhaseState[];
  subagents?: Array<{ name: string; status: string; goal: string }>;
  onPhaseClick?: (phase: PhaseName) => void;
}

const PHASE_DEFS: Record<PhaseName, { label: string; conditional: boolean; gate: boolean }> = {
  enter:   { label: "ENTER",   conditional: false, gate: false },
  analyze: { label: "ANALYZE", conditional: false, gate: false },
  setup:   { label: "SETUP",   conditional: true,  gate: false },
  work:    { label: "WORK",    conditional: false, gate: false },
  review:  { label: "REVIEW",  conditional: false, gate: true },
  publish: { label: "PUBLISH", conditional: true,  gate: false },
  persist: { label: "PERSIST", conditional: false, gate: false },
};

const PHASE_ORDER: PhaseName[] = ["enter", "analyze", "setup", "work", "review", "publish", "persist"];

// SVG layout constants
const NODE_W = 100;
const NODE_H = 44;
const COL_GAP = 24;
const ROW_Y: Record<PhaseName, number> = {
  enter: 20, analyze: 20, setup: 20, work: 20, review: 20, publish: 20, persist: 20,
};
// For WORK phase, we need extra height for subagent fan-out
const WORK_EXTRA_H = 100;
const SUBAGENT_Y = NODE_H + 30;

function PhaseNode({
  name, status, percent, label, conditional, gate, x, y, isActive, onClick,
}: {
  name: PhaseName; status: PhaseState["status"]; percent: number;
  label: string; conditional: boolean; gate: boolean;
  x: number; y: number; isActive: boolean; onClick?: () => void;
}) {
  const isRunning = status === "running";
  const isPassed = status === "passed";
  const isFailed = status === "failed";
  const isSkipped = status === "skipped";
  const isPending = status === "pending";

  const fill = isRunning ? "rgba(52,211,153,0.12)" :
               isPassed ? "rgba(52,211,153,0.08)" :
               isFailed ? "rgba(248,113,113,0.08)" :
               isSkipped ? "rgba(113,113,122,0.05)" :
               "rgba(113,113,122,0.03)";

  const stroke = isRunning ? "#34d399" :
                 isPassed ? "rgba(52,211,153,0.3)" :
                 isFailed ? "#f87171" :
                 isSkipped ? "rgba(113,113,122,0.2)" :
                 "rgba(113,113,122,0.12)";

  const textColor = isRunning ? "#34d399" :
                    isPassed ? "rgba(52,211,153,0.7)" :
                    isFailed ? "#f87171" :
                    isSkipped ? "rgba(113,113,122,0.4)" :
                    "rgba(113,113,122,0.4)";

  return (
    <g
      onClick={onClick}
      className={cn("cursor-pointer transition-opacity", isPending ? "opacity-40" : "")}
      style={isActive && isRunning ? { filter: "drop-shadow(0 0 12px rgba(52,211,153,0.15))" } : {}}
    >
      {/* Node body */}
      <rect
        x={x} y={y} width={NODE_W} height={NODE_H} rx={12} ry={12}
        fill={fill} stroke={stroke} strokeWidth={conditional ? 1.5 : 1}
        strokeDasharray={conditional ? "4 3" : "none"}
      />
      {isRunning && (
        <rect
          x={x} y={y} width={NODE_W} height={NODE_H} rx={12} ry={12}
          fill="none" stroke="rgba(52,211,153,0.3)" strokeWidth={1}
          className="animate-pulse"
        />
      )}

      {/* Status dot */}
      {isRunning && (
        <circle cx={x + 14} cy={y + NODE_H / 2} r={4} fill="#34d399">
          <animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite" />
        </circle>
      )}
      {isPassed && <CheckCircle x={x + 12} y={y + (NODE_H - 10) / 2} width={10} height={10} stroke="rgba(52,211,153,0.5)" strokeWidth={1.5} />}
      {isFailed && <XCircle x={x + 12} y={y + (NODE_H - 10) / 2} width={10} height={10} stroke="#f87171" strokeWidth={1.5} />}
      {isSkipped && <SkipForward x={x + 12} y={y + (NODE_H - 10) / 2} width={10} height={10} stroke="rgba(113,113,122,0.4)" strokeWidth={1.5} />}

      {/* Label */}
      <text
        x={x + NODE_W / 2} y={y + NODE_H / 2 + 4}
        textAnchor="middle" dominantBaseline="middle"
        fill={textColor} fontSize={11} fontWeight={700}
        fontFamily="JetBrains Mono, SF Mono, monospace"
        letterSpacing={1}
      >
        {label}
      </text>

      {/* Gate indicator */}
      {gate && (
        <>
          <rect x={x + NODE_W - 6} y={y - 6} width={12} height={12} rx={3} fill="#f59e0b" />
          <text x={x + NODE_W} y={y} textAnchor="middle" dominantBaseline="middle" fill="#0a0a0f" fontSize={8} fontWeight={700}>!</text>
        </>
      )}

      {/* Conditional marker */}
      {conditional && (
        <text
          x={x + NODE_W / 2} y={y + NODE_H + 12}
          textAnchor="middle" fill="rgba(113,113,122,0.3)" fontSize={8}
          fontFamily="JetBrains Mono, SF Mono, monospace"
        >
          ?
        </text>
      )}

      {/* Running progress bar */}
      {isRunning && percent > 0 && (
        <rect
          x={x + 8} y={y + NODE_H - 4}
          width={(NODE_W - 16) * (percent / 100)} height={2} rx={1}
          fill="#34d399"
        />
      )}
    </g>
  );
}

function ConnectorLine({ x1, y1, x2, y2, passed }: { x1: number; y1: number; x2: number; y2: number; passed: boolean }) {
  const midX = (x1 + x2) / 2;
  const path = `M${x1 + NODE_W / 2},${y1 + NODE_H} L${midX},${y1 + NODE_H} L${midX},${y2} L${x2 + NODE_W / 2},${y2}`;

  return (
    <g>
      <path d={path} fill="none" stroke="rgba(113,113,122,0.12)" strokeWidth={1.5} />
      {passed && (
        <path
          d={path} fill="none" stroke="rgba(52,211,153,0.3)" strokeWidth={1.5}
          strokeDasharray="6 3" strokeLinecap="round"
        >
          <animate attributeName="stroke-dashoffset" values="0;-18" dur="1s" repeatCount="indefinite" />
        </path>
      )}
    </g>
  );
}

function SubagentNode({ x, y, name, status, goal }: { x: number; y: number; name: string; status: string; goal: string }) {
  const isRunning = status === "running";
  const isDone = status === "completed" || status === "passed";
  const isFailed = status === "failed";

  return (
    <g className="cursor-default">
      <rect
        x={x} y={y} width={84} height={28} rx={8}
        fill={isRunning ? "rgba(52,211,153,0.08)" : isDone ? "rgba(52,211,153,0.04)" : isFailed ? "rgba(248,113,113,0.06)" : "rgba(113,113,122,0.03)"}
        stroke={isRunning ? "rgba(52,211,153,0.25)" : isDone ? "rgba(52,211,153,0.12)" : isFailed ? "rgba(248,113,113,0.2)" : "rgba(113,113,122,0.08)"}
        strokeWidth={1}
      />
      <text
        x={x + 42} y={y + 14}
        textAnchor="middle" dominantBaseline="middle"
        fill={isRunning ? "#34d399" : isDone ? "rgba(52,211,153,0.6)" : isFailed ? "#f87171" : "rgba(113,113,122,0.4)"}
        fontSize={9} fontFamily="JetBrains Mono, SF Mono, monospace"
      >
        {name}
      </text>
      {goal && (
        <text
          x={x + 42} y={y + 38}
          textAnchor="middle" fill="rgba(113,113,122,0.3)" fontSize={7}
          fontFamily="JetBrains Mono, SF Mono, monospace"
        >
          {goal.length > 18 ? goal.slice(0, 18) + "..." : goal}
        </text>
      )}
    </g>
  );
}

export function PipelineDag({ phases, subagents, onPhaseClick }: PipelineDagProps) {
  const phaseMap = useMemo(() => {
    const map = new Map<PhaseName, PhaseState>();
    for (const p of phases) map.set(p.name, p);
    return map;
  }, [phases]);

  const activeIdx = PHASE_ORDER.findIndex((n) => phaseMap.get(n)?.status === "running");

  // Layout calculations
  const svgW = PHASE_ORDER.length * (NODE_W + COL_GAP) + COL_GAP;
  const phaseCount = subagents && subagents.length > 0 ? 1 : 0;
  const svgH = phaseCount > 0 ? NODE_H + WORK_EXTRA_H + 40 : NODE_H + 60;

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5 overflow-x-auto">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-7 h-7 rounded-xl bg-emerald-500/10 flex items-center justify-center">
          <GitFork className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
        </div>
        <span className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Pipeline DAG</span>
        <div className="flex items-center gap-3 ml-auto text-[10px] text-zinc-600">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" /> running
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400/50" /> passed
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-zinc-700" /> pending
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-400" /> failed
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded border border-dashed border-zinc-600 bg-transparent" /> conditional
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-amber-400 text-[6px] flex items-center justify-center text-black font-bold">!</span> HITL gate
          </span>
        </div>
      </div>

      <svg width={svgW} height={svgH} className="w-full" style={{ minHeight: svgH }}>
        {/* Connectors between phases */}
        {PHASE_ORDER.slice(0, -1).map((name, idx) => {
          const next = PHASE_ORDER[idx + 1];
          const cur = phaseMap.get(name);
          const phasePassed = cur?.status === "passed";
          const x1 = idx * (NODE_W + COL_GAP);
          const x2 = (idx + 1) * (NODE_W + COL_GAP);
          const y1 = ROW_Y[name];
          const y2 = ROW_Y[next];
          return (
            <ConnectorLine
              key={`conn-${name}-${next}`}
              x1={x1} y1={y1} x2={x2} y2={y2}
              passed={phasePassed || (activeIdx > idx)}
            />
          );
        })}

        {/* Phase nodes */}
        {PHASE_ORDER.map((name, idx) => {
          const state = phaseMap.get(name) ?? {
            name, label: PHASE_DEFS[name].label, status: "pending" as const, percent: 0,
          };
          const def = PHASE_DEFS[name];
          const x = idx * (NODE_W + COL_GAP) + 10;
          const y = ROW_Y[name];
          return (
            <PhaseNode
              key={name}
              name={name}
              status={state.status}
              percent={state.percent}
              label={def.label}
              conditional={def.conditional}
              gate={def.gate}
              x={x} y={y}
              isActive={activeIdx === idx}
              onClick={() => onPhaseClick?.(name)}
            />
          );
        })}

        {/* Subagent fan-out within WORK phase */}
        {subagents && subagents.length > 0 && (
          <>
            {/* Vertical connector from WORK to subagents */}
            <line
              x1={3 * (NODE_W + COL_GAP) + 10 + NODE_W / 2}
              y1={ROW_Y.work + NODE_H}
              x2={3 * (NODE_W + COL_GAP) + 10 + NODE_W / 2}
              y2={SUBAGENT_Y}
              stroke="rgba(113,113,122,0.12)" strokeWidth={1}
            />
            {/* Horizontal bar */}
            <line
              x1={3 * (NODE_W + COL_GAP) + 10 + NODE_W / 2 - (subagents.length * 60)}
              y1={SUBAGENT_Y}
              x2={3 * (NODE_W + COL_GAP) + 10 + NODE_W / 2 + (subagents.length * 60)}
              y2={SUBAGENT_Y}
              stroke="rgba(113,113,122,0.12)" strokeWidth={1}
            />
            {/* Subagent nodes */}
            {subagents.map((sa, i) => {
              const saX = 3 * (NODE_W + COL_GAP) + 10 + NODE_W / 2 - ((subagents.length - 1) * 46) / 2 + i * 46;
              return (
                <g key={sa.name}>
                  <line
                    x1={saX + 42} y1={SUBAGENT_Y}
                    x2={saX + 42} y2={SUBAGENT_Y + 10}
                    stroke="rgba(113,113,122,0.08)" strokeWidth={1}
                  />
                  <SubagentNode
                    x={saX} y={SUBAGENT_Y + 10}
                    name={sa.name}
                    status={sa.status}
                    goal={sa.goal}
                  />
                </g>
              );
            })}
            {/* Arrow back up from subagents */}
            {subagents.filter(s => s.status === "completed" || s.status === "passed").length > 0 && (
              <path
                d={`M${3 * (NODE_W + COL_GAP) + 10 + NODE_W / 2},${SUBAGENT_Y + 38} L${3 * (NODE_W + COL_GAP) + 10 + NODE_W / 2},${SUBAGENT_Y + 50}`}
                fill="none" stroke="rgba(52,211,153,0.2)" strokeWidth={1}
                markerEnd="url(#arrow-green)"
              />
            )}
          </>
        )}

        {/* Arrow marker definitions */}
        <defs>
          <marker id="arrow-green" markerWidth={6} markerHeight={6} refX={6} refY={3} orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="rgba(52,211,153,0.2)" />
          </marker>
        </defs>
      </svg>
    </div>
  );
}
