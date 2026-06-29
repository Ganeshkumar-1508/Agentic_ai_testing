"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import {
  ChevronRight,
  File,
  FolderClosed,
  FolderOpen,
  FileCode,
  FileText,
  Image,
  Terminal,
  type LucideIcon,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface FileTreeNode {
  path: string;
  type: "file" | "directory";
  mime?: string;
  size?: number;
  children?: FileTreeNode[];
}

export interface FileExplorerProps {
  tree: FileTreeNode | null;
  onFileSelect?: (path: string) => void;
  selectedFile?: string;
  className?: string;
}

// ─── Icon selector ────────────────────────────────────────────────────────────

function getFileIcon(mime?: string): LucideIcon {
  if (!mime) return File;
  if (mime.startsWith("text/")) return FileText;
  if (mime.startsWith("image/")) return Image;
  if (mime.includes("javascript") || mime.includes("typescript") || mime.includes("python")) return FileCode;
  if (mime.includes("terminal") || mime.includes("shell")) return Terminal;
  return File;
}

// ─── Node Component ───────────────────────────────────────────────────────────

function TreeNode(props: {
  node: FileTreeNode;
  depth?: number;
  onFileSelect?: (path: string) => void;
  selectedFile?: string;
  key?: string;
}) {
  const { node, depth = 0, onFileSelect, selectedFile } = props;
  const [isOpen, setIsOpen] = useState(depth < 1); // auto-open root
  const isDir = node.type === "directory";
  const isSelected = node.path === selectedFile;
  const FileIcon = getFileIcon(node.mime);

  const handleClick = () => {
    if (isDir) {
      setIsOpen(!isOpen);
    } else {
      onFileSelect?.(node.path);
    }
  };

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        className={cn(
          "w-full flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-all text-left",
          "hover:bg-white/[0.04]",
          isSelected && "bg-emerald-500/10 text-emerald-300",
          !isSelected && "text-neutral-400",
        )}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        {/* Chevron for directories */}
        {isDir ? (
          <ChevronRight
            className={cn(
              "w-3 h-3 shrink-0 text-neutral-600 transition-transform",
              isOpen && "rotate-90",
            )}
            strokeWidth={1.5}
          />
        ) : (
          <span className="w-3 shrink-0" />
        )}

        {/* Icon */}
        {isDir ? (
          isOpen ? (
            <FolderOpen className="w-3.5 h-3.5 shrink-0 text-amber-400" strokeWidth={1.5} />
          ) : (
            <FolderClosed className="w-3.5 h-3.5 shrink-0 text-amber-400" strokeWidth={1.5} />
          )
        ) : (
          <FileIcon className="w-3.5 h-3.5 shrink-0 text-neutral-500" strokeWidth={1.5} />
        )}

        {/* Name */}
        <span className="truncate flex-1">
          {node.path === "." ? "logs" : node.path.split("/").pop()}
        </span>

        {/* Size */}
        {!isDir && node.size != null && (
          <span className="text-[10px] text-neutral-600 shrink-0">
            {node.size < 1024 ? `${node.size}B` : `${(node.size / 1024).toFixed(0)}KB`}
          </span>
        )}
      </button>

      {/* Children */}
      {isDir && isOpen && node.children && (
        <div>
          {node.children.map((child, i) => (
            <TreeNode
              key={`${child.path}-${i}`}
              node={child}
              depth={depth + 1}
              onFileSelect={onFileSelect}
              selectedFile={selectedFile}
            />
          ))}
          {node.children.length === 0 && (
            <p className="text-[10px] text-neutral-600 pl-12 py-1">Empty</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function FileExplorer({ tree, onFileSelect, selectedFile, className }: FileExplorerProps) {
  if (!tree) {
    return (
      <div className={cn("flex items-center justify-center py-8 text-xs text-neutral-600", className)}>
        No logs available
      </div>
    );
  }

  return (
    <div className={cn("overflow-y-auto", className)}>
      <div className="px-3 py-2 border-b border-white/[0.05]">
        <p className="text-[10px] font-medium text-neutral-500 uppercase tracking-wider">
          Run Artifacts
        </p>
      </div>
      <TreeNode node={tree} onFileSelect={onFileSelect} selectedFile={selectedFile} />
    </div>
  );
}
