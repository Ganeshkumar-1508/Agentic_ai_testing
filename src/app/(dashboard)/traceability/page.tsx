"use client";

import { useMemo, useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { GitBranch, Activity, ShieldAlert, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/PageHeader";
import { ProjectPicker, useActiveProjectId } from "@/components/shared/ProjectPicker";
import {
  Toolbar,
  buildEmptyFilters,
  type TraceFilters,
} from "./_components/Toolbar";
import { TraceabilityGraph } from "./_components/TraceabilityGraph";
import { TraceabilityMatrix } from "./_components/TraceabilityMatrix";
import { TraceabilityTable } from "./_components/TraceabilityTable";
import { InspectorDrawer, type InspectorSelection } from "./_components/InspectorDrawer";
import { RequirementForm } from "./_components/RequirementForm";
import { GenerateDialog } from "./_components/GenerateDialog";
import { TraceabilityEmptyState } from "./_components/EmptyStateCustom";
import { buildGraphModel } from "./_components/graph-model";
import {
  useRequirements,
  useMatrix,
  useCoverageGaps,
  useDefects,
  useRiskScores,
} from "./_components/use-traceability";
import type { ViewMode, LayoutDirection, Requirement, MatrixRow } from "./_components/types";

function parseNodeId(id: string): { kind: "requirement" | "test" | "defect" | "gap"; rawId: string } | null {
  const [prefix, ...rest] = id.split(":");
  if (prefix === "req" || prefix === "test" || prefix === "defect" || prefix === "gap") {
    const kind = prefix === "req" ? "requirement" : prefix;
    return { kind, rawId: rest.join(":") };
  }
  return null;
}

export default function TraceabilityPage() {
  const qc = useQueryClient();
  const projectId = useActiveProjectId();

  useEffect(() => {
    const onProjectChange = () => {
      qc.invalidateQueries({ queryKey: ["trace-requirements"] });
      qc.invalidateQueries({ queryKey: ["trace-gaps"] });
      qc.invalidateQueries({ queryKey: ["trace-matrix"] });
      qc.invalidateQueries({ queryKey: ["trace-risk"] });
      qc.invalidateQueries({ queryKey: ["trace-defects"] });
      qc.invalidateQueries({ queryKey: ["trace-requirement"] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      setSelection(null);
      setFilters(buildEmptyFilters());
    };
    window.addEventListener("testai:active-project-changed", onProjectChange);
    return () => window.removeEventListener("testai:active-project-changed", onProjectChange);
  }, [qc]);

  const reqs = useRequirements();
  const matrix = useMatrix();
  const gaps = useCoverageGaps();
  const defects = useDefects();
  const risks = useRiskScores();

  const [view, setView] = useState<ViewMode>("graph");
  const [direction, setDirection] = useState<LayoutDirection>("TB");
  const [depth, setDepth] = useState(3);
  const [filters, setFilters] = useState<TraceFilters>(buildEmptyFilters());
  const [selection, setSelection] = useState<InspectorSelection>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Requirement | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  const allReqs = reqs.data?.requirements ?? [];
  const allMatrix = matrix.data?.matrix ?? [];
  const allDefects = defects.data?.defects ?? [];
  const allGaps = gaps.data?.gaps ?? [];

  const filteredMatrix = useMemo<MatrixRow[]>(() => {
    if (!filters.query && filters.statuses.size === 0 && filters.priorities.size === 0) return allMatrix;
    return allMatrix.filter((r) => {
      const req = allReqs.find((x) => x.id === r.requirement_id);
      const matchesText =
        !filters.query ||
        r.title.toLowerCase().includes(filters.query.toLowerCase()) ||
        r.tests.some((t) => t.name.toLowerCase().includes(filters.query.toLowerCase()));
      const matchesPriority = filters.priorities.size === 0 || (req && filters.priorities.has(req.priority));
      const matchesStatus =
        filters.statuses.size === 0 || (req && filters.statuses.has(req.status));
      return matchesText && matchesPriority && matchesStatus;
    });
  }, [allMatrix, allReqs, filters]);

  const model = useMemo(
    () => buildGraphModel(allReqs, filteredMatrix, allDefects, allGaps),
    [allReqs, filteredMatrix, allDefects, allGaps]
  );

  const stats = useMemo(() => {
    const total = allReqs.length;
    const covered = allReqs.length - allGaps.filter((g) => g.has_gap).length;
    const verified = allGaps.filter((g) => !g.has_gap).length;
    const openDefects = allDefects.length;
    const highRisk = (risks.data?.scores ?? []).filter((s) => s.risk_score >= 70).length;
    return { total, covered, verified, openDefects, highRisk };
  }, [allReqs, allGaps, allDefects, risks.data]);

  const handleSelectNode = (nodeId: string) => {
    const parsed = parseNodeId(nodeId);
    if (!parsed) return;
    if (parsed.kind === "requirement") {
      setSelection({ kind: "requirement", id: parsed.rawId });
    } else if (parsed.kind === "test") {
      const t = filteredMatrix.flatMap((r) => r.tests).find((x) => x.id === parsed.rawId);
      if (t) {
        setSelection({
          kind: "test",
          id: parsed.rawId,
          reqId: (t as { requirement_id?: string }).requirement_id ?? "",
          testStatus: t.status,
        });
      } else {
        setSelection({ kind: "test", id: parsed.rawId, reqId: "", testStatus: "pending" });
      }
    } else if (parsed.kind === "defect") {
      const d = allDefects.find((x) => x.defect_id === parsed.rawId);
      setSelection({
        kind: "defect",
        id: parsed.rawId,
        testName: d?.test_name ?? null,
        status: d?.status ?? null,
        reqId: d?.requirement_id ?? null,
      });
    } else if (parsed.kind === "gap") {
      setSelection({ kind: "gap", id: parsed.rawId, reqId: parsed.rawId.replace(/^gap:/, "") });
    }
  };

  const handleSelectRequirement = (id: string) => setSelection({ kind: "requirement", id });
  const handleSelectTest = (testId: string, reqId: string) => {
    for (const r of filteredMatrix) {
      const t = r.tests.find((x) => x.id === testId);
      if (t) {
        setSelection({ kind: "test", id: testId, reqId: r.requirement_id, testStatus: t.status });
        return;
      }
    }
    setSelection({ kind: "test", id: testId, reqId, testStatus: "pending" });
  };

  const onEdit = (req: Requirement) => {
    setEditing(req);
    setFormOpen(true);
  };

  const resultCount =
    view === "graph" ? model.nodes.length : view === "matrix" ? filteredMatrix.length : filteredMatrix.length + allDefects.length;

  return (
    <div className="space-y-6">
      <PageHeader
        label="COVERAGE"
        description="Follow each requirement through linked tests, runs, and defects."
        actions={
          <div className="flex items-center gap-3">
            <StatBar stats={stats} />
            <span className="h-4 w-px bg-white/[0.06]" />
            <ProjectPicker />
          </div>
        }
      />

      <Toolbar
        filters={filters}
        onFiltersChange={setFilters}
        view={view}
        onViewChange={setView}
        direction={direction}
        onDirectionChange={setDirection}
        depth={depth}
        onDepthChange={setDepth}
        onAdd={() => {
          setEditing(null);
          setFormOpen(true);
        }}
        onGenerate={() => setGenerateOpen(true)}
        resultCount={resultCount}
      />

      {allReqs.length === 0 ? (
        <TraceabilityEmptyState
          onAdd={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          onGenerate={() => setGenerateOpen(true)}
        />
      ) : view === "graph" ? (
        <TraceabilityGraph
          key={`${resetKey}-${direction}-${depth}`}
          model={model}
          direction={direction}
          onSelect={handleSelectNode}
          onReset={() => setResetKey((k) => k + 1)}
        />
      ) : view === "matrix" ? (
        <TraceabilityMatrix
          rows={filteredMatrix}
          onSelectRequirement={handleSelectRequirement}
          onSelectTest={(id) => handleSelectTest(id, "")}
        />
      ) : (
        <TraceabilityTable
          rows={filteredMatrix}
          requirements={allReqs}
          defects={allDefects}
          onSelectRequirement={handleSelectRequirement}
          onSelectTest={(id) => handleSelectTest(id, "")}
        />
      )}

      <InspectorDrawer
        selection={selection}
        onClose={() => setSelection(null)}
        onEdit={onEdit}
        onSelectTest={handleSelectTest}
        onSelectRequirement={handleSelectRequirement}
      />

      <RequirementForm
        open={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        initial={editing}
      />

      <GenerateDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        selectedRequirementIds={selection?.kind === "requirement" ? [selection.id] : []}
      />
    </div>
  );
}

function StatBar({ stats }: { stats: { total: number; covered: number; verified: number; openDefects: number; highRisk: number } }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.4 }}
      className="flex items-center gap-4 text-[10.5px] font-mono"
    >
      <Stat label="reqs" value={stats.total} icon={GitBranch} />
      <span className="text-neutral-700">·</span>
      <Stat label="covered" value={stats.covered} icon={ShieldCheck} tone="emerald" />
      <span className="text-neutral-700">·</span>
      <Stat label="gaps" value={stats.total - stats.covered} icon={ShieldAlert} tone="rose" />
      <span className="text-neutral-700">·</span>
      <Stat label="defects" value={stats.openDefects} icon={Activity} tone="rose" />
    </motion.div>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  tone?: "neutral" | "emerald" | "rose";
}) {
  const toneClass = {
    neutral: "text-neutral-300",
    emerald: "text-emerald-300",
    rose: "text-rose-300",
  }[tone];
  return (
    <span className="flex items-center gap-1.5 text-neutral-500">
      <Icon className={cn("w-3 h-3", toneClass)} strokeWidth={1.5} />
      <span className="text-neutral-600 uppercase tracking-wider">{label}</span>
      <span className={cn("tabular-nums", toneClass)}>{value}</span>
    </span>
  );
}
