"use client";

import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  GitBranch,
  Play,
  Loader2,
  FileText,
  X,
  ChevronDown,
  CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

interface WorkflowInputProps {
  requirements: string;
  onRequirementsChange: (value: string) => void;
  files: File[];
  onFilesChange: (files: File[]) => void;
  githubRepo: string;
  onGithubRepoChange: (value: string) => void;
  onStart: () => void;
  isRunning: boolean;
  workflowProgress?: number;
}

const ACCEPTED_EXTENSIONS = [".tsx", ".jsx", ".ts", ".js", ".py", ".go", ".rs", ".java", ".cs"];

export function WorkflowInput({
  requirements,
  onRequirementsChange,
  files,
  onFilesChange,
  githubRepo,
  onGithubRepoChange,
  onStart,
  isRunning,
  workflowProgress = 0,
}: WorkflowInputProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const droppedFiles = Array.from(e.dataTransfer.files);
      const validFiles = droppedFiles.filter((f) =>
        ACCEPTED_EXTENSIONS.some((ext) => f.name.endsWith(ext))
      );
      if (validFiles.length > 0) {
        onFilesChange([...files, ...validFiles]);
      } else {
        toast.error("No valid source files dropped");
      }
    },
    [files, onFilesChange]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = Array.from(e.target.files || []);
      if (selectedFiles.length > 0) {
        onFilesChange([...files, ...selectedFiles]);
      }
    },
    [files, onFilesChange]
  );

  const removeFile = useCallback(
    (index: number) => {
      const updated = files.filter((_, i) => i !== index);
      onFilesChange(updated);
    },
    [files, onFilesChange]
  );

  const handleSubmit = useCallback(() => {
    if (!requirements.trim()) {
      toast.error("Please enter requirements before starting analysis");
      return;
    }
    onStart();
  }, [requirements, onStart]);

  if (isRunning) {
    return (
      <Collapsible defaultOpen className="bg-surface border border-border rounded-xl shadow-card">
        <CollapsibleTrigger className="flex w-full items-center justify-between p-8 group">
          <div className="flex items-center gap-4">
            <Loader2 className="w-5 h-5 text-emerald-400 animate-spin" strokeWidth={1.5} />
            <div className="text-left">
              <p className="text-sm font-medium text-foreground">Analysis Running</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Requirements submitted — pipeline in progress
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-emerald-400/80 tabular-nums">{workflowProgress}%</span>
            <ChevronDown className="w-4 h-4 text-muted-foreground group-data-[state=open]:rotate-180 transition-transform" strokeWidth={1.5} />
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-8 pb-8 pt-2 border-t border-border">
            <p className="text-xs text-muted-foreground mb-3">Submitted requirements</p>
            <p className="text-sm text-foreground/80 line-clamp-3">{requirements}</p>
            {files.length > 0 && (
              <p className="text-xs text-muted-foreground mt-3">{files.length} file(s) attached</p>
            )}
            {githubRepo && (
              <p className="text-xs text-muted-foreground mt-1">Repo: {githubRepo}</p>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-xl p-8 shadow-card">
      <h2 className="text-lg font-medium text-foreground mb-1">New Analysis</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Describe what you want to test and optionally attach source files or link a repository.
      </p>

      {/* Requirements Textarea */}
      <div className="mb-5">
        <label className="block text-xs font-medium text-muted-foreground mb-2">
          Requirements
        </label>
        <Textarea
          value={requirements}
          onChange={(e) => onRequirementsChange(e.target.value)}
          placeholder="Describe what you want to test..."
          className="min-h-[120px] bg-black/20 border-border text-foreground placeholder:text-muted-foreground/40 resize-none rounded-lg"
        />
      </div>

      {/* File Upload Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "relative mb-4 cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-all duration-200",
          isDragOver
            ? "border-emerald-400/40 bg-emerald-400/5"
            : "border-border bg-black/10 hover:border-border-hover"
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          onChange={handleFileSelect}
          className="hidden"
        />
        <Upload
          className="mx-auto w-6 h-6 text-muted-foreground mb-2"
          strokeWidth={1.5}
        />
        <p className="text-sm text-muted-foreground">
          Drag & drop source files here, or click to browse
        </p>
        <p className="text-xs text-muted-foreground/50 mt-1">
          .tsx, .jsx, .ts, .js, .py, .go, .rs, .java, .cs
        </p>
      </div>

      {/* Attached Files */}
      {files.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-2">
          {files.map((file, index) => (
            <span
              key={`${file.name}-${index}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white/[0.05] border border-border text-xs text-foreground"
            >
              <FileText className="w-3.5 h-3.5 text-muted-foreground" strokeWidth={1.5} />
              {file.name}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeFile(index);
                }}
                className="ml-0.5 text-muted-foreground/50 hover:text-foreground transition-colors"
              >
                <X className="w-3 h-3" strokeWidth={1.5} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* GitHub Repo URL */}
      <div className="mb-6">
        <label className="block text-xs font-medium text-muted-foreground mb-2">
          GitHub Repository <span className="text-muted-foreground/50">(optional)</span>
        </label>
        <div className="relative">
          <GitBranch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
          <Input
            value={githubRepo}
            onChange={(e) => onGithubRepoChange(e.target.value)}
            placeholder="https://github.com/user/repo"
            className="pl-10 bg-black/20 border-border text-foreground placeholder:text-muted-foreground/40 rounded-lg"
          />
        </div>
      </div>

      {/* Start Button */}
      <Button
        onClick={handleSubmit}
        disabled={isRunning}
        className="w-full h-11 rounded-lg bg-emerald-500 hover:bg-emerald-400 active:scale-[0.98] text-black font-medium transition-all duration-200"
      >
        <Play className="w-4 h-4" strokeWidth={1.5} />
        Start Analysis
      </Button>
    </div>
  );
}
