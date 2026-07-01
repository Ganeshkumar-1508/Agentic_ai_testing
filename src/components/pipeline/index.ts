/**
 * Pipeline components — organized by sub-domain.
 *
 * Sub-domains:
 * - execution: EventStream, PipelineDag, StageProgress, etc.
 * - results: TestResults, GroupedErrors, MetricsBar, CostMeter, etc.
 * - config: ModeSelector, AdvancedPipelineConfig, PipelineTemplates, etc.
 * - sandbox/: SandboxTerminal, SandboxFileTree, SandboxResources, etc.
 * - delegation/: DelegationInspector
 *
 * Import from the specific sub-domain for clarity:
 *   import { EventStream } from "@/components/pipeline"
 *   import { SandboxTerminal } from "@/components/pipeline/sandbox"
 */

// ── Execution ───────────────────────────────────────────────────────
export { EventStream } from "./EventStream";
export { PipelineDag } from "./PipelineDag";
export { StageProgress } from "./StageProgress";
export { ToolTimeline } from "./ToolTimeline";
export { ToolCallTimeline } from "./ToolCallTimeline";
export { CheckpointTimeline } from "./CheckpointTimeline";
export { PhaseProgressBar } from "./PhaseProgressBar";
export { SessionReplay } from "./SessionReplay";

// ── Results & Metrics ───────────────────────────────────────────────
export { TestResults } from "./TestResults";
export { TestResultsTable } from "./TestResultsTable";
export { GroupedErrors } from "./GroupedErrors";
export { MetricsBar } from "./MetricsBar";
export { CostMeter } from "./CostMeter";
export { ModelTokensPanel } from "./ModelTokensPanel";
export { PipelineSummary } from "./PipelineSummary";
export { AISummaryBanner } from "./AISummaryBanner";

// ── Configuration ───────────────────────────────────────────────────
export { ModeSelector } from "./ModeSelector";
export { AdvancedPipelineConfig } from "./AdvancedPipelineConfig";
export { PipelineTemplates } from "./PipelineTemplates";
export { SavedFilters } from "./SavedFilters";
export { BatchRerun } from "./BatchRerun";

// ── Panels ──────────────────────────────────────────────────────────
export { ApprovalPanel } from "./ApprovalPanel";
export { SubAgentPanel } from "./SubAgentPanel";
export { HealHistoryPanel } from "./HealHistoryPanel";
export { SkillsPanel } from "./SkillsPanel";
export { KanbanBoardSection } from "./KanbanBoardSection";
export { RunArtifactBrowser } from "./RunArtifactBrowser";
export { RunHeader } from "./RunHeader";
export { ReleaseTracking } from "./ReleaseTracking";

// ── Sub-domains (import directly) ───────────────────────────────────
// sandbox/ — 10 components for sandbox management
// delegation/ — DelegationInspector
