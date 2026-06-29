"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  FileCode, FileJson, FileText, FileType, FolderOpen,
  ChevronDown, ChevronRight, Download, Eye, Terminal, BarChart3,
} from "lucide-react";

interface ArtifactItem {
  name: string;
  type: "file" | "folder";
  path: string;
  mime?: string;
  size?: number;
  content?: string;
  children?: ArtifactItem[];
}

interface RunArtifactBrowserProps {
  testResults?: Array<{
    testName: string;
    status: string;
    error?: string;
    durationMs?: number;
  }>;
  coverageReports?: Array<{
    id: string;
    language: string;
    framework: string;
    lineCoverage: number;
    totalLines: number;
    createdAt?: string;
  }>;
  logs?: Array<{
    type: string;
    data?: any;
    createdAt?: string;
  }>;
  isLoading?: boolean;
}

function FileIcon({ name, mime }: { name: string; mime?: string }) {
  if (mime?.startsWith("text/html") || name.endsWith(".html")) return <FileCode className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />;
  if (name.endsWith(".json") || mime === "application/json") return <FileJson className="w-4 h-4 text-amber-400" strokeWidth={1.5} />;
  if (name.endsWith(".ts") || name.endsWith(".tsx") || name.endsWith(".js") || name.endsWith(".jsx") || name.endsWith(".py"))
    return <FileCode className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />;
  if (name.endsWith(".md")) return <FileText className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />;
  if (name.endsWith(".log") || name.endsWith(".txt")) return <Terminal className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />;
  if (name.includes("lcov") || name.includes("coverage")) return <BarChart3 className="w-4 h-4 text-blue-400" strokeWidth={1.5} />;
  return <FileType className="w-4 h-4 text-zinc-500" strokeWidth={1.5} />;
}

function buildPreviewContent(item: ArtifactItem, allTestResults: RunArtifactBrowserProps["testResults"], allCoverage: RunArtifactBrowserProps["coverageReports"]): string | null {
  if (item.content) return item.content;
  if (item.name.endsWith(".json")) return JSON.stringify({ note: "Binary or external file — download to view" }, null, 2);

  const covMatch = item.name.match(/^coverage-(.+)\.(.+)$/);
  if (covMatch) {
    const report = allCoverage?.find(c => c.language === covMatch[1]);
    if (report) {
      return [
        `Coverage Report — ${report.language} (${report.framework})`,
        `Line Coverage: ${report.lineCoverage}%`,
        `Total Lines: ${report.totalLines}`,
        `Generated: ${report.createdAt ?? "unknown"}`,
      ].join("\n");
    }
  }

  const testMatch = item.name.match(/^(.+)\.(test\.tsx|test\.ts|spec\.ts|spec\.py)$/);
  if (testMatch) {
    const results = allTestResults?.filter(t => t.testName.includes(testMatch[1]));
    if (results && results.length > 0) {
      return results.map(r =>
        `${r.status === "passed" ? "PASS" : "FAIL"}  ${r.testName}  (${r.durationMs ?? 0}ms)${r.error ? `\n  ${r.error}` : ""}`
      ).join("\n");
    }
  }

  return null;
}

export function RunArtifactBrowser({ testResults, coverageReports, logs, isLoading }: RunArtifactBrowserProps) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(["test-results", "coverage"]));
  const [tab, setTab] = useState<"files" | "preview">("files");

  const artifactTree = useMemo(() => {
    const tree: ArtifactItem[] = [];

    // Test results folder
    if (testResults && testResults.length > 0) {
      const children: ArtifactItem[] = testResults.map(t => ({
        name: `${t.testName.replace(/[\/:]/g, "-")}.result.json`,
        type: "file" as const,
        path: `test-results/${t.testName.replace(/[\/:]/g, "-")}`,
        mime: "application/json",
        content: JSON.stringify(t, null, 2),
      }));
      tree.push({ name: "test-results", type: "folder", path: "test-results", children });
    }

    // Coverage folder
    if (coverageReports && coverageReports.length > 0) {
      const children: ArtifactItem[] = coverageReports.map(c => ({
        name: `coverage-${c.language}.${c.framework}`,
        type: "file" as const,
        path: `coverage/${c.language}-${c.framework}`,
        mime: "text/plain",
        content: [
          `Coverage Report — ${c.language} (${c.framework})`,
          `Line Coverage: ${c.lineCoverage}%`,
          `Total Lines: ${c.totalLines}`,
          `Generated: ${c.createdAt ?? "unknown"}`,
        ].join("\n"),
      }));
      tree.push({ name: "coverage", type: "folder", path: "coverage", children });
    }

    // Logs folder
    if (logs && logs.length > 0) {
      const children: ArtifactItem[] = logs.slice(0, 50).map((l, i) => ({
        name: `event-${i.toString().padStart(4, "0")}.log`,
        type: "file" as const,
        path: `logs/event-${i}`,
        mime: "text/plain",
        content: `[${l.createdAt ?? ""}] ${l.type}\n${JSON.stringify(l.data ?? {}, null, 2)}`,
      }));
      tree.push({ name: "logs", type: "folder", path: "logs", children });
    }

    return tree;
  }, [testResults, coverageReports, logs]);

  const selectedItem = useMemo(() => {
    if (!selectedPath) return null;
    const find = (items: ArtifactItem[]): ArtifactItem | null => {
      for (const item of items) {
        if (item.path === selectedPath) return item;
        if (item.children) {
          const found = find(item.children);
          if (found) return found;
        }
      }
      return null;
    };
    return find(artifactTree);
  }, [selectedPath, artifactTree]);

  const previewContent = selectedItem ? buildPreviewContent(selectedItem, testResults, coverageReports) : null;

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5 space-y-3">
        <div className="w-32 h-4 rounded-full shimmer-bg" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 h-48">
          <div className="col-span-1 bg-white/[0.02] rounded-xl animate-pulse" />
          <div className="col-span-2 bg-white/[0.02] rounded-xl animate-pulse" />
        </div>
      </div>
    );
  }

  if (artifactTree.length === 0) {
    return null;
  }

  const hasCoverage = coverageReports && coverageReports.length > 0;
  const hasLogs = logs && logs.length > 0;
  const totalArtifacts = (testResults?.length ?? 0) + (coverageReports?.length ?? 0) + (logs?.length ?? 0);

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl overflow-hidden">
      <div className="flex items-center justify-between p-4 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <FolderOpen className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
          </div>
          <span className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Artifacts</span>
          <span className="text-[10px] font-mono text-zinc-600 px-1.5 py-0.5 rounded bg-white/[0.03]">{totalArtifacts}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 border-t border-white/[0.05]">
        {/* File tree */}
        <div className="col-span-1 border-r border-white/[0.05] p-2 max-h-80 overflow-y-auto">
          {artifactTree.map((folder) => (
            <div key={folder.path}>
              <button
                onClick={() => toggleFolder(folder.path)}
                className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.03] transition-colors"
              >
                {expandedFolders.has(folder.path)
                  ? <ChevronDown className="w-3 h-3" strokeWidth={1.5} />
                  : <ChevronRight className="w-3 h-3" strokeWidth={1.5} />
                }
                <FolderOpen className="w-3.5 h-3.5" strokeWidth={1.5} />
                {folder.name}
                <span className="ml-auto text-[9px] text-zinc-600 font-mono">{folder.children?.length}</span>
              </button>
              <AnimatePresence>
                {expandedFolders.has(folder.path) && folder.children && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    {folder.children.map((file) => (
                      <button
                        key={file.path}
                        onClick={() => { setSelectedPath(file.path); setTab("preview"); }}
                        className={cn(
                          "w-full flex items-center gap-2 pl-7 pr-2 py-1.5 rounded-lg text-xs transition-colors",
                          selectedPath === file.path
                            ? "bg-emerald-500/10 text-emerald-400"
                            : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.02]",
                        )}
                      >
                        <FileIcon name={file.name} mime={file.mime} />
                        <span className="truncate">{file.name}</span>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>

        {/* Preview pane */}
        <div className="col-span-1 md:col-span-2 p-0">
          {tab === "preview" && selectedItem && previewContent ? (
            <div className="max-h-80 overflow-y-auto">
              <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.05] bg-white/[0.01]">
                <span className="text-[10px] font-mono text-zinc-500">{selectedItem.name}</span>
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-zinc-700 px-1 py-0.5 rounded bg-white/[0.03] font-mono">
                    {selectedItem.mime ?? "text/plain"}
                  </span>
                </div>
              </div>
              <pre className="p-4 text-[11px] font-mono text-zinc-400 leading-relaxed overflow-x-auto whitespace-pre-wrap break-all">
                {previewContent}
              </pre>
            </div>
          ) : tab === "preview" && selectedItem ? (
            <div className="flex items-center justify-center h-48 text-xs text-zinc-600">
              No preview available
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-48 text-xs text-zinc-600 gap-2">
              <FolderOpen className="w-8 h-8 text-zinc-800" strokeWidth={1} />
              <span>Select a file to preview</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
