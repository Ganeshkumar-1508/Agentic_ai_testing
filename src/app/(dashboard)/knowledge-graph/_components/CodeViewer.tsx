"use client";

import { useEffect, useState } from "react";
import { Highlight, themes, type PrismTheme } from "prism-react-renderer";
import { Loader2, FileText, ExternalLink, Hash } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileContentResponse } from "./types";

const customDark: PrismTheme = {
  plain: {
    color: "#e5e7eb",
    backgroundColor: "transparent",
  },
  styles: [
    { types: ["comment", "prolog", "doctype", "cdata"], style: { color: "#6b7280", fontStyle: "italic" } },
    { types: ["punctuation"], style: { color: "#9ca3af" } },
    {
      types: ["property", "tag", "constant", "symbol", "deleted"],
      style: { color: "#f87171" },
    },
    { types: ["boolean", "number"], style: { color: "#fbbf24" } },
    { types: ["selector", "attr-name", "string", "char", "builtin", "inserted"], style: { color: "#34d399" } },
    { types: ["operator", "entity", "url", "variable"], style: { color: "#a3a3a3" } },
    { types: ["atrule", "attr-value", "keyword"], style: { color: "#a78bfa" } },
    { types: ["function", "class-name"], style: { color: "#60a5fa" } },
    { types: ["regex", "important"], style: { color: "#fb923c" } },
  ],
};

export function CodeViewer({
  data,
  isLoading,
  isError,
}: {
  data: FileContentResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  const [highlightReady, setHighlightReady] = useState(false);

  useEffect(() => {
    setHighlightReady(true);
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-6 py-12 text-[12px] text-neutral-500">
        <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
        Loading source…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
        <FileText className="w-5 h-5 text-neutral-700" strokeWidth={1.2} />
        <div className="text-[12px] text-neutral-500">Failed to load file content.</div>
      </div>
    );
  }

  if (data.content == null) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
        <div className="w-8 h-8 rounded-full bg-amber-500/10 border border-amber-400/20 flex items-center justify-center">
          <FileText className="w-4 h-4 text-amber-300" strokeWidth={1.5} />
        </div>
        <div className="space-y-1.5 max-w-md">
          <div className="text-[13px] text-neutral-200">Source not stored locally</div>
          <div className="text-[11.5px] text-neutral-500 leading-relaxed">
            The knowledge graph references this file, but the source code isn&apos;t snapshotted
            in the backend. View it on GitHub if the repo is public.
          </div>
        </div>
        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-400/20 text-[12px] text-emerald-200 hover:bg-emerald-500/[0.15] transition-colors"
          >
            <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
            View on GitHub
          </a>
        )}
        <div className="mt-2 text-[10px] font-mono text-neutral-600">
          {data.path} · {data.language}
        </div>
      </div>
    );
  }

  if (!highlightReady) {
    return (
      <div className="flex items-center gap-2 px-6 py-12 text-[12px] text-neutral-500">
        <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
        Preparing syntax highlighter…
      </div>
    );
  }

  return (
    <div className="relative">
      {data.truncated && (
        <div className="sticky top-0 z-10 px-4 py-1.5 bg-amber-500/10 border-b border-amber-400/20 text-[10.5px] font-mono text-amber-200 flex items-center gap-1.5">
          <Hash className="w-3 h-3" strokeWidth={1.5} />
          file truncated (showing first 512 KB)
        </div>
      )}
      <Highlight theme={customDark} code={data.content} language={mapLanguage(data.language)}>
        {({ className, style, tokens, getLineProps, getTokenProps }) => (
          <pre
            className={cn(
              className,
              "text-[12px] leading-[1.6] font-mono overflow-x-auto p-4 m-0"
            )}
            style={{ ...style, background: "transparent" }}
          >
            {tokens.map((line, i) => {
              const lineNumber = i + 1;
              return (
                <div
                  key={i}
                  {...getLineProps({ line })}
                  className="flex items-start gap-3 group"
                >
                  <span
                    className="select-none text-right text-neutral-600 text-[10.5px] tabular-nums shrink-0 w-10 pt-0.5 group-hover:text-neutral-400 transition-colors"
                    aria-hidden
                  >
                    {lineNumber}
                  </span>
                  <span className="flex-1 min-w-0">
                    {line.map((token, key) => (
                      <span key={key} {...getTokenProps({ token })} />
                    ))}
                  </span>
                </div>
              );
            })}
          </pre>
        )}
      </Highlight>
    </div>
  );
}

function mapLanguage(lang: string): string {
  const map: Record<string, string> = {
    python: "python",
    typescript: "typescript",
    tsx: "tsx",
    javascript: "javascript",
    jsx: "jsx",
    json: "json",
    markdown: "markdown",
    yaml: "yaml",
    toml: "toml",
    bash: "bash",
    go: "go",
    rust: "rust",
    java: "java",
    kotlin: "kotlin",
    ruby: "ruby",
    css: "css",
    scss: "scss",
    html: "markup",
    sql: "sql",
    xml: "markup",
    text: "text",
  };
  return map[lang] ?? "text";
}
