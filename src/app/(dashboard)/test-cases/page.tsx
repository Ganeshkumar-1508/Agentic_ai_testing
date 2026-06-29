"use client";

import { Suspense, useState, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { TestFilterBar, type FilterStatus } from "@/components/shared/TestFilterBar";
import { KpiRow } from "@/components/shared/KpiRow";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import {
  Search, Beaker, FileText, CheckCircle, XCircle, Clock,
  FolderClosed, FolderOpen, ChevronRight, Code, AlertCircle, Play, TestTube,
  AlertTriangle, Activity, Shield, RefreshCw, Download, TrendingUp, TestTube as LoadIcon, Eye,
  Loader2, Zap,
} from "lucide-react";
import { TestPlanList } from "@/components/test-plans/TestPlanList";
import { FlakyTab, VisualTab, LoadTab } from "./_tabs";
import { toast } from "sonner";
import { api } from "@/lib/api/api-client";

const TEST_TABS = [
  { id: "", label: "All Tests", icon: Beaker },
  { id: "flaky", label: "Flaky", icon: AlertTriangle },
  { id: "visual", label: "Visual", icon: Eye },
  { id: "load", label: "Load", icon: LoadIcon },
];

interface TestCase {
  id: string;
  name: string;
  type: string;
  status: string;
  content?: string | null;
  code?: string | null;
  codeLanguage?: string | null;
  description?: string | null;
  createdAt: string;
  priority?: string;
  duration?: number | null;
  errorMessage?: string | null;
  steps?: unknown;
  expected?: string | null;
  testData?: unknown;
}

interface FolderDef {
  id: string;
  label: string;
  types: string[] | null;
  icon: typeof FolderClosed;
}

const DEFAULT_FOLDERS: FolderDef[] = [
  { id: "all", label: "All Tests", types: null, icon: FolderClosed },
  { id: "unit", label: "Unit Tests", types: ["unit"], icon: FolderClosed },
  { id: "integration", label: "Integration Tests", types: ["api"], icon: FolderClosed },
  { id: "e2e", label: "E2E Tests", types: ["ui"], icon: FolderClosed },
  { id: "performance", label: "Performance", types: ["performance"], icon: FolderClosed },
  { id: "security", label: "Security", types: ["security"], icon: FolderClosed },
];

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle; label: string; className: string }> = {
  passed: {
    icon: CheckCircle,
    label: "Passed",
    className: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  },
  failed: {
    icon: XCircle,
    label: "Failed",
    className: "text-red-400 bg-red-500/10 border-red-500/20",
  },
  pending: {
    icon: Clock,
    label: "Pending",
    className: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  },
  running: {
    icon: Clock,
    label: "Running",
    className: "text-zinc-400 bg-zinc-500/10 border-zinc-500/20",
  },
};

const DEFAULT_STATUS = {
  icon: Clock,
  label: "Unknown",
  className: "text-neutral-400 bg-white/[0.03] border-white/[0.08]",
};

function getStatusConfig(status: string) {
  return STATUS_CONFIG[status.toLowerCase()] || DEFAULT_STATUS;
}

const TYPE_CONFIG: Record<string, { label: string; className: string }> = {
  unit: {
    label: "Unit",
    className: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
  },
  api: {
    label: "Integration",
    className: "bg-zinc-500/10 text-zinc-300 border-zinc-500/20",
  },
  ui: {
    label: "E2E",
    className: "bg-zinc-500/10 text-zinc-300 border-zinc-500/20",
  },
  performance: {
    label: "Performance",
    className: "bg-amber-500/10 text-amber-300 border-amber-500/20",
  },
  security: {
    label: "Security",
    className: "bg-red-500/10 text-red-300 border-red-500/20",
  },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type.toLowerCase()] || {
    label: type,
    className: "bg-white/[0.05] text-neutral-300 border-white/[0.08]",
  };
}

function formatDate(dateStr: string) {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function TestCasesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = searchParams?.get("tab") || "";
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFolder, setActiveFolder] = useState("all");
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [customFolders, setCustomFolders] = useState<any[]>([]);
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");

  const fetchTestCases = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [tcData, pData, folderData] = await Promise.all([
        api.get<any>("/api/testcases?project_id=default-project").catch(() => ({} as any)),
        api.get<{ sessions?: any[] }>("/api/sessions?source=pipeline&limit=50").catch(() => ({ sessions: [] })),
        api.get<{ folders?: any[] }>("/api/testcases/folders").catch(() => ({ folders: [] })),
      ]);

      const raw: any[] = (tcData?.test_cases ?? tcData?.testCases ?? []) as any[];

      if (raw.length === 0 && (pData?.sessions ?? []).length > 0) {
        for (const s of pData.sessions ?? []) {
          raw.push({
            id: s.id,
            name: s.goal || s.prompt || s.id?.slice(0, 12),
            test_type: "pipeline",
            status: s.status === "completed" ? "passed" : s.status === "failed" ? "failed" : "pending",
            description: s.goal ? `Pipeline: ${s.goal.slice(0, 80)}` : "",
            code: null,
            code_language: null,
            created_at: s.created_at || s.createdAt || "",
            priority: "",
            duration_ms: null,
            error_message: null,
          });
        }
      }

      setTestCases(raw.map((r: any) => ({
        id: r.id,
        name: r.name ?? "",
        type: r.test_type ?? r.type ?? "",
        status: r.status ?? "",
        content: r.content ?? null,
        code: r.code ?? null,
        codeLanguage: r.code_language ?? r.codeLanguage ?? null,
        description: r.description ?? null,
        createdAt: r.created_at ?? r.createdAt ?? "",
        priority: r.priority ?? "",
        duration: r.duration_ms ?? r.duration ?? null,
        errorMessage: r.error_message ?? r.errorMessage ?? null,
        steps: r.steps ?? null,
        expected: r.expected ?? r.expected_result ?? null,
        testData: r.test_data ?? r.testData ?? null,
      })));

      setCustomFolders(folderData?.folders ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTestCases();
  }, [fetchTestCases]);

  const allFolders: FolderDef[] = [
    ...DEFAULT_FOLDERS,
    ...customFolders.map((f: any) => ({
      id: f.id, label: f.name, types: f.filter_types || null, icon: FolderClosed,
    })),
  ];
  const activeFolderDef = allFolders.find((f) => f.id === activeFolder) || allFolders[0];

  const filteredTestCases = testCases.filter((tc) => {
    if (activeFolderDef.types !== null && !activeFolderDef.types.includes(tc.type)) {
      return false;
    }
    if (filterStatus !== "all" && tc.status !== filterStatus) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        tc.name.toLowerCase().includes(q) ||
        tc.type.toLowerCase().includes(q) ||
        tc.description?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const folderCounts = allFolders.reduce(
    (acc, f) => {
      if (f.types === null) {
        acc[f.id] = testCases.length;
      } else {
        acc[f.id] = testCases.filter((tc) => f.types!.includes(tc.type)).length;
      }
      return acc;
    },
    {} as Record<string, number>
  );

  const statsCards = [
    {
      label: "Total Tests",
      value: testCases.length,
      icon: Beaker,
      color: "text-emerald-400",
    },
    {
      label: "Passed",
      value: testCases.filter((t) => t.status === "passed").length,
      icon: CheckCircle,
      color: "text-emerald-400",
    },
    {
      label: "Failed",
      value: testCases.filter((t) => t.status === "failed").length,
      icon: XCircle,
      color: "text-red-400",
    },
    {
      label: "Pending",
      value: testCases.filter((t) => t.status === "pending").length,
      icon: Clock,
      color: "text-amber-400",
    },
    {
      label: "Flaky",
      value: testCases.filter((t) => t.status === "flaky").length,
      icon: AlertTriangle,
      color: "text-amber-400",
    },
    {
      label: "Avg Duration",
      value: testCases.filter((t) => t.duration).length > 0
        ? `${Math.round(testCases.filter((t) => t.duration).reduce((s, t) => s + (t.duration || 0), 0) / testCases.filter((t) => t.duration).length / 1000)}s`
        : "0s",
      icon: Clock,
      color: "text-zinc-400",
    },
  ];

  const getCodeContent = (tc: TestCase): string => {
    return tc.code || tc.content || "";
  };

  const getCodeLanguage = (tc: TestCase): string => {
    return tc.codeLanguage || "typescript";
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          description="Manage, organize, and execute your test suite with AI-powered generation and self-healing."
        />

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5 space-y-3"
            >
              <SkeletonBlock className="w-10 h-10 rounded-xl" />
              <SkeletonBlock className="h-8 w-16" />
              <SkeletonBlock className="h-4 w-20" />
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-6">
          <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-4 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonBlock key={i} className="h-10 w-full rounded-[1rem]" />
            ))}
          </div>
          <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-6 space-y-4">
            <SkeletonBlock className="h-10 w-full rounded-[1rem]" />
            <SkeletonBlock className="h-64 w-full rounded-[1.5rem]" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader
          description="Review, run, and manage AI-generated test cases"
        />
        <ErrorState message={error} onRetry={fetchTestCases} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <PageHeader
          description="Review, run, and manage AI-generated test cases"
        />
        <div className="flex items-center gap-2">
          <button onClick={() => router.push("/pipeline")}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-[12px] font-semibold bg-emerald-500 text-zinc-950 hover:bg-emerald-400 transition-all active:scale-[0.98]">
            <Zap className="w-3.5 h-3.5" strokeWidth={2} /> Generate with AI
          </button>
          <div className="flex bg-card border border-white/[0.06] rounded-full p-0.5 gap-0.5">
            {TEST_TABS.map((t) => {
              const TabIcon = t.icon;
              return (
                <button key={t.id} onClick={() => {
                  const params = new URLSearchParams(searchParams?.toString());
                  if (t.id) params.set("tab", t.id); else params.delete("tab");
                  router.push(`/test-cases?${params.toString()}`);
                }}
                  className={`px-3 py-1.5 rounded-full text-[11px] font-medium transition-all flex items-center gap-1.5 ${
                    activeTab === t.id ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-500 hover:text-zinc-300"
                  }`}>
                  <TabIcon className="w-3 h-3" strokeWidth={1.5} />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {activeTab === "flaky" ? (
        <FlakyTab />
      ) : activeTab === "visual" ? (
        <VisualTab />
      ) : activeTab === "load" ? (
        <LoadTab />
      ) : (
        <>
      {/* AI Test Generation collapsible */}
      <details className="bg-surface border border-white/[0.05] rounded-3xl overflow-hidden group">
        <summary className="flex items-center gap-3 px-6 py-4 cursor-pointer select-none hover:bg-white/[0.02] transition-colors">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <Zap className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          </div>
          <div className="flex-1">
            <span className="text-sm font-semibold text-zinc-100">AI Test Generation</span>
            <p className="text-[11px] text-neutral-500 mt-0.5">Generate test cases from requirements, code, or descriptions</p>
          </div>
          <ChevronRight className="w-4 h-4 text-neutral-500 transition-transform group-open:rotate-90" strokeWidth={1.5} />
        </summary>
        <div className="px-6 pb-5 border-t border-white/[0.05] pt-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button onClick={() => router.push("/pipeline")}
              className="flex items-center gap-3 p-4 rounded-2xl border border-white/[0.06] hover:border-emerald-500/20 hover:bg-emerald-500/5 transition-all text-left">
              <Play className="w-5 h-5 text-emerald-400" strokeWidth={1.5} />
              <div>
                <div className="text-[13px] font-medium text-neutral-200">Generate from description</div>
                <div className="text-[11px] text-neutral-500 mt-0.5">Describe what to test</div>
              </div>
            </button>
            <button onClick={() => router.push("/requirements")}
              className="flex items-center gap-3 p-4 rounded-2xl border border-white/[0.06] hover:border-emerald-500/20 hover:bg-emerald-500/5 transition-all text-left">
              <FileText className="w-5 h-5 text-blue-400" strokeWidth={1.5} />
              <div>
                <div className="text-[13px] font-medium text-neutral-200">From requirements</div>
                <div className="text-[11px] text-neutral-500 mt-0.5">Link to traced requirements</div>
              </div>
            </button>
            <button onClick={() => router.push("/traceability")}
              className="flex items-center gap-3 p-4 rounded-2xl border border-white/[0.06] hover:border-emerald-500/20 hover:bg-emerald-500/5 transition-all text-left">
              <Code className="w-5 h-5 text-emerald-400" strokeWidth={1.5} />
              <div>
                <div className="text-[13px] font-medium text-neutral-200">From code analysis</div>
                <div className="text-[11px] text-neutral-500 mt-0.5">Analyze source and generate</div>
              </div>
            </button>
          </div>
        </div>
      </details>

      <TestPlanList />

      <KpiRow items={[
        { label: "Total Tests", value: testCases.length },
        { label: "Passed", value: testCases.filter((t) => t.status === "passed").length },
        { label: "Failed", value: testCases.filter((t) => t.status === "failed").length },
        { label: "Pending", value: testCases.filter((t) => t.status === "pending").length },
      ]} />

      <TestFilterBar
        search={searchQuery}
        onSearchChange={setSearchQuery}
        status={filterStatus}
        onStatusChange={setFilterStatus}
        total={filteredTestCases.length}
      />

      {testCases.length === 0 ? (
        <EmptyState
          icon={Beaker}
          title="No Test Cases Yet"
          description="Run a pipeline to generate real test cases, then they will appear here."
          action={{
            label: "Go to Pipeline",
            onClick: () => router.push("/pipeline"),
          }}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr_380px] gap-6">
          <div className="bg-surface border border-white/[0.05] rounded-3xl p-3 h-fit">
            <div className="flex items-center justify-between px-3 py-2">
              <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider">Folders</p>
              <button type="button" onClick={() => setShowNewFolder(!showNewFolder)}
                className="text-neutral-500 hover:text-neutral-300 transition-colors active:scale-[0.95]">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
              </button>
            </div>
            <div className="space-y-1">
              {showNewFolder && (
                <div className="px-3 pb-2">
                    <input value={newFolderName} onChange={(e) => setNewFolderName(e.target.value)}
                    onKeyDown={async (e) => {
                      if (e.key === "Enter" && newFolderName.trim()) {
                        try {
                          await api.post("/api/testcases/folders", { name: newFolderName.trim(), filter_types: [] });
                          toast.success("Folder created");
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Failed to create folder");
                        }
                        setNewFolderName(""); setShowNewFolder(false);
                        fetchTestCases();
                      }
                    }}
                    placeholder="Folder name..." className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 outline-none focus:border-emerald-500/40" autoFocus />
                </div>
              )}
              {allFolders.map((folder) => {
                const FolderIcon = activeFolder === folder.id ? FolderOpen : FolderClosed;
                const count = folderCounts[folder.id] || 0;
                return (
                  <button
                    key={folder.id}
                    type="button"
                    onClick={() => setActiveFolder(folder.id)}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-3 py-2.5 rounded-[1rem] text-sm transition-all duration-200",
                      activeFolder === folder.id
                        ? "bg-emerald-500/10 text-emerald-300 border-l-[3px] border-emerald-400"
                        : "text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03] border-l-[3px] border-transparent"
                    )}
                  >
                    <FolderIcon className="w-4 h-4 shrink-0" strokeWidth={1.5} />
                    <span className="flex-1 text-left">{folder.label}</span>
                    <span
                      className={cn(
                        "text-xs font-medium px-1.5 py-0.5 rounded-md",
                        activeFolder === folder.id
                          ? "bg-emerald-500/15 text-emerald-300"
                          : "bg-white/[0.04] text-neutral-500"
                      )}
                    >
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="bg-surface border border-white/[0.05] rounded-3xl overflow-hidden flex flex-col">
            <div className="p-4 border-b border-white/[0.05]">
              <div className="relative">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-500"
                  strokeWidth={1.5}
                />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search test cases..."
                  className="pl-10 bg-white/[0.02] border-white/[0.08] text-neutral-100 placeholder:text-neutral-600 rounded-[1rem]"
                />
              </div>
            </div>

            <div className="px-4 py-3 border-b border-white/[0.05]">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-neutral-400">{activeFolderDef.label}</span>
                <ChevronRight className="w-3 h-3 text-neutral-600" strokeWidth={1.5} />
                <span className="text-neutral-500">{filteredTestCases.length} test{filteredTestCases.length !== 1 ? "s" : ""}</span>
              </div>
            </div>

            <ScrollArea className="flex-1">
              {filteredTestCases.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
                  <Search className="w-12 h-12 text-neutral-600 mb-4" strokeWidth={1.2} />
                  <p className="text-neutral-300 font-medium mb-1">No matches found</p>
                  <p className="text-sm text-neutral-500">
                    Try adjusting your search or folder filter
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.05]">
                  {filteredTestCases.map((tc) => {
                    const StatusIcon = getStatusConfig(tc.status).icon;
                    const isSelected = selectedTestCase?.id === tc.id;

                    return (
                      <button
                        key={tc.id}
                        type="button"
                        onClick={() => setSelectedTestCase(tc)}
                        className={cn(
                          "w-full text-left px-4 py-4 transition-all duration-200 hover:bg-white/[0.02]",
                          isSelected && "bg-emerald-500/[0.03] border-l-2 border-l-emerald-400"
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <div
                            className={cn(
                              "w-9 h-9 rounded-[0.75rem] flex items-center justify-center shrink-0 mt-0.5",
                              getTypeConfig(tc.type).className
                            )}
                          >
                            <TestTube className="w-4 h-4" strokeWidth={1.5} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-medium text-zinc-100 truncate">
                                {tc.name}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge
                                variant="outline"
                                className={cn(
                                  "text-[10px] px-1.5 py-0 rounded border font-medium",
                                  getTypeConfig(tc.type).className
                                )}
                              >
                                {getTypeConfig(tc.type).label}
                              </Badge>
                              <StatusIcon
                                className={cn(
                                  "w-3.5 h-3.5",
                                  tc.status === "running" ? "animate-spin" : ""
                                )}
                                strokeWidth={2}
                              />
                              <span
                                className={cn(
                                  "text-xs",
                                  getStatusConfig(tc.status).className.split(" ")[0]
                                )}
                              >
                                {getStatusConfig(tc.status).label}
                              </span>
                              <span className="text-[10px] text-neutral-500 ml-auto">
                                {formatDate(tc.createdAt)}
                              </span>
                            </div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </div>

          <div className="bg-surface border border-white/[0.05] rounded-3xl overflow-hidden h-fit lg:sticky lg:top-24">
            {selectedTestCase ? (
              <div className="flex flex-col h-full">
                <div className="p-5 border-b border-white/[0.05]">
                  <div className="flex items-start gap-3 mb-3">
                    <div
                      className={cn(
                        "w-10 h-10 rounded-[0.75rem] flex items-center justify-center shrink-0",
                        getTypeConfig(selectedTestCase.type).className
                      )}
                    >
                      <TestTube className="w-5 h-5" strokeWidth={1.5} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-base font-semibold text-zinc-100 leading-tight">
                        {selectedTestCase.name}
                      </h3>
                      {selectedTestCase.description && (
                        <p className="text-sm text-neutral-400 mt-1 line-clamp-2">
                          {selectedTestCase.description}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-xs px-2 py-0.5 rounded font-medium border",
                        getTypeConfig(selectedTestCase.type).className
                      )}
                    >
                      {getTypeConfig(selectedTestCase.type).label}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-xs px-2 py-0.5 rounded font-medium border",
                        getStatusConfig(selectedTestCase.status).className
                      )}
                    >
                      {getStatusConfig(selectedTestCase.status).label}
                    </Badge>
                    {selectedTestCase.priority && (
                      <Badge
                        variant="outline"
                        className="text-xs px-2 py-0.5 rounded font-medium border border-white/[0.08] text-neutral-400"
                      >
                        {selectedTestCase.priority}
                      </Badge>
                    )}
                    <button
                      onClick={async () => {
                        try {
                          const data = await api.post<{ success?: boolean; error?: string }>(`/api/testcases/${selectedTestCase.id}/run`);
                          if (data?.success) {
                            toast.success("Test passed");
                          } else {
                            toast.error(data?.error || "Test failed");
                          }
                        } catch {
                          toast.error("Failed to run test");
                        }
                      }}
                      className="flex items-center gap-1 px-2.5 py-1 text-[10px] rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.97]"
                    >
                      <Play size={11} strokeWidth={1.5} />
                      Run
                    </button>
                  </div>

                  <div className="mt-3 flex items-center gap-4 text-xs text-neutral-500">
                    <span>
                      Created: {formatDate(selectedTestCase.createdAt)}
                    </span>
                    {selectedTestCase.duration != null && (
                      <span>
                        Duration: {(selectedTestCase.duration / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex-1">
                  {getCodeContent(selectedTestCase) ? (
                    <div className="p-0">
                      <div className="flex items-center gap-2 px-5 py-3 border-b border-white/[0.05]">
                        <Code
                          className="w-4 h-4 text-neutral-500"
                          strokeWidth={1.5}
                        />
                        <span className="text-xs font-medium text-neutral-400 uppercase tracking-wider">
                          {getCodeLanguage(selectedTestCase)}
                        </span>
                        <span className="text-xs text-neutral-600">|</span>
                        <span className="text-xs text-neutral-500">
                          {getCodeContent(selectedTestCase).split("\n").length} lines
                        </span>
                      </div>
                      <ScrollArea className="h-[420px]">
                        <pre className="text-xs text-neutral-300 font-mono leading-relaxed whitespace-pre-wrap bg-white/[0.02] p-4">
                          {getCodeContent(selectedTestCase)}
                        </pre>
                      </ScrollArea>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
                      <FileText
                        className="w-10 h-10 text-neutral-600 mb-3"
                        strokeWidth={1.2}
                      />
                      <p className="text-sm text-neutral-400 font-medium">
                        No code available
                      </p>
                      <p className="text-xs text-neutral-500 mt-1">
                        This test case has no generated code yet.
                      </p>
                    </div>
                  )}
                </div>

                {selectedTestCase.errorMessage && (
                  <div className="mx-5 mb-5 p-4 bg-red-500/10 border border-red-500/20 rounded-[1rem]">
                    <div className="flex items-start gap-2">
                      <AlertCircle
                        className="w-4 h-4 text-red-400 shrink-0 mt-0.5"
                        strokeWidth={1.5}
                      />
                      <div>
                        <p className="text-sm font-medium text-red-300 mb-1">
                          Execution Error
                        </p>
                        <p className="text-xs text-red-400 font-mono whitespace-pre-wrap break-all">
                          {selectedTestCase.errorMessage}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Steps */}
                {Array.isArray(selectedTestCase.steps) && (selectedTestCase.steps as string[]).length > 0 && (
                  <div className="mx-5 mb-5">
                    <div className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">Steps</div>
                    <div className="space-y-2">
                      {(selectedTestCase.steps as string[]).map((step: string, i: number) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-neutral-400">
                          <span className="text-neutral-600 font-mono shrink-0">{i + 1}.</span>
                          <span>{step}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Expected Result */}
                {typeof selectedTestCase.expected === "string" && selectedTestCase.expected && (
                  <div className="mx-5 mb-5">
                    <div className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">Expected Result</div>
                    <p className="text-xs text-neutral-400 leading-relaxed">{selectedTestCase.expected}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
                <div className="w-14 h-14 rounded-[1rem] bg-white/[0.03] flex items-center justify-center mb-4">
                  <ChevronRight className="w-7 h-7 text-neutral-500" strokeWidth={1.2} />
                </div>
                <p className="text-neutral-300 font-medium mb-1">
                  Select a Test Case
                </p>
                <p className="text-sm text-neutral-500">
                  Choose a test case from the list to view its details
                </p>
              </div>
            )}
          </div>
        </div>
      )}
      </>
      )}
    </div>
  );
}


export default function TestCasesPage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] flex items-center justify-center bg-background"><div className="flex items-center gap-3 text-zinc-600"><Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} /><span className="text-sm">Loading test cases...</span></div></div>}>
      <TestCasesPageInner />
    </Suspense>
  );
}
