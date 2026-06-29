"use client";

import { useEffect, useRef, useState } from "react";

interface MermaidDiagramProps {
  chart: string;
}

export function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function render() {
      try {
        const { default: mermaid } = await import("mermaid");
        if (cancelled) return;

        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          themeVariables: {
            primaryColor: "#1e293b",
            primaryTextColor: "#e2e8f0",
            primaryBorderColor: "#334155",
            lineColor: "#64748b",
            secondaryColor: "#0f172a",
            tertiaryColor: "#1e293b",
          },
        });

        const { svg } = await mermaid.render("mermaid-" + Math.random().toString(36).slice(2), chart);
        if (cancelled) return;
        if (ref.current) {
          ref.current.innerHTML = svg;
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to render diagram");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    render();
    return () => { cancelled = true; };
  }, [chart]);

  if (error) {
    return (
      <div className="my-3 p-3 rounded-lg border border-red-900/30 bg-red-950/10">
        <p className="text-[11px] font-mono text-red-400/80">{error}</p>
      </div>
    );
  }

  return (
    <div className="my-4 flex justify-center">
      {loading && (
        <div className="w-full max-w-md h-32 rounded-lg bg-zinc-900/50 animate-pulse" />
      )}
      <div ref={ref} className={loading ? "hidden" : "max-w-full overflow-x-auto [&_svg]:max-w-full"} />
    </div>
  );
}
