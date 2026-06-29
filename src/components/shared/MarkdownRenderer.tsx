"use client";

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Copy, Check } from "lucide-react";
import { toast } from "sonner";
import type { Components } from "react-markdown";
import { MermaidDiagram } from "./MermaidDiagram";
import {
  capMarkdownNesting,
  normalizeStreamdownMathMarkdown,
  preprocessStreamdownMarkdown,
} from "@/lib/streamdown";

function ShikiCodeBlock({ className, children }: { className?: string; children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const [html, setHtml] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const text = Array.isArray(children) ? children.join("") : typeof children === "string" ? children : "";
  const match = /language-(\w+)/.exec(className || "");
  const lang = match?.[1] || "text";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { codeToHtml } = await import("shiki");
        if (cancelled) return;
        const result = await codeToHtml(text, { lang, theme: "vesper" });
        if (!cancelled) setHtml(result);
      } catch {
        if (!cancelled) setHtml(`<pre>${text}</pre>`);
      }
    })();
    return () => { cancelled = true; };
  }, [text, lang]);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("Code copied");
    setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <div className="my-3 group/code">
      <div className="flex items-center justify-between bg-zinc-900/90 border border-zinc-800/50 border-b-0 rounded-t-lg px-4 py-1.5">
        <span className="text-[10px] text-zinc-600 font-mono">{lang}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors opacity-0 group-hover/code:opacity-100 active:scale-[0.97]"
        >
          {copied ? <><Check size={10} strokeWidth={1.5} className="text-emerald-400" /> Copied</> : <><Copy size={10} strokeWidth={1.5} /> Copy</>}
        </button>
      </div>
      <div
        ref={ref}
        className="overflow-x-auto [&_pre]:!m-0 [&_pre]:!rounded-none [&_pre]:!rounded-b-lg [&_pre]:!px-4 [&_pre]:!py-3 text-[12px]"
        dangerouslySetInnerHTML={html ? { __html: html } : undefined}
      >
        {!html && <pre className="bg-zinc-900/50 px-4 py-3 text-xs text-zinc-400">{text}</pre>}
      </div>
    </div>
  );
}

const components: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || "");
    const inline = !match;
    if (inline) {
      return (
        <code
          className="bg-white/[0.06] px-1.5 py-0.5 rounded text-[13px] font-mono text-emerald-300"
          {...props}
        >
          {children}
        </code>
      );
    }
    return <ShikiCodeBlock className={className}>{children}</ShikiCodeBlock>;
  },
  p({ children }) {
    return <p className="text-sm text-neutral-400 leading-relaxed mb-3 last:mb-0">{children}</p>;
  },
  h1({ children }) {
    return <h1 className="text-lg font-semibold text-neutral-100 mb-3 mt-6 first:mt-0">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-base font-semibold text-neutral-100 mb-2 mt-5 first:mt-0">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-sm font-semibold text-neutral-200 mb-2 mt-4">{children}</h3>;
  },
  ul({ children }) {
    return <ul className="list-disc list-inside text-sm text-neutral-400 space-y-1 mb-3">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="list-decimal list-inside text-sm text-neutral-400 space-y-1 mb-3">{children}</ol>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-emerald-400/30 pl-4 italic text-neutral-500 mb-3">
        {children}
      </blockquote>
    );
  },
  a({ href, children }) {
    return <a href={href} className="text-emerald-400/80 hover:text-emerald-300 underline underline-offset-2" target="_blank" rel="noreferrer">{children}</a>;
  },
  table({ children }) {
    return <div className="overflow-x-auto my-3"><table className="w-full text-xs border-collapse border border-zinc-800/30">{children}</table></div>;
  },
  th({ children }) {
    return <th className="border border-zinc-800/30 px-3 py-2 bg-zinc-900/50 text-left font-medium text-neutral-200">{children}</th>;
  },
  td({ children }) {
    return <td className="border border-zinc-800/30 px-3 py-2 text-neutral-400">{children}</td>;
  },
  hr() {
    return <div className="border-t border-zinc-800/30 my-4" />;
  },
  pre({ children }) {
    return <div className="mb-3 last:mb-0">{children}</div>;
  },
};

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const processed = useMemo(() => {
    let md = content;
    md = capMarkdownNesting(md);
    md = normalizeStreamdownMathMarkdown(md);
    md = preprocessStreamdownMarkdown(md);
    return md;
  }, [content]);

  const enhanced: Components = useMemo(() => ({
    ...components,
    code({ className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || "");
      const lang = match?.[1] || "";
      if (lang === "mermaid") {
        const chart = Array.isArray(children) ? children.join("") : String(children);
        return <MermaidDiagram chart={chart} />;
      }
      try {
        const codeFn = components.code as any;
        if (typeof codeFn === "function") {
          return codeFn({ className, children, ...props });
        }
      } catch {}
      return <code className={className} {...props}>{children}</code>;
    },
  }), []);

  return (
    <div className={className}>
      <ReactMarkdown components={enhanced}>{processed}</ReactMarkdown>
    </div>
  );
}

export function AgentOutput({ output }: { output: unknown }) {
  if (!output) return null;
  const text = typeof output === "string" ? output : JSON.stringify(output, null, 2);

  if (text.includes("```") || text.includes("#") || text.includes("**")) {
    return <MarkdownRenderer content={text} />;
  }

  return (
    <pre className="text-[11px] font-mono text-neutral-400 whitespace-pre-wrap break-all leading-relaxed">
      {text}
    </pre>
  );
}
