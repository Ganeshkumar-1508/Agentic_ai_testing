import type { ReactNode } from "react";

interface Section {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}

export function PageShell({ title, description, actions, sections }: {
  title: string;
  description?: string;
  actions?: ReactNode;
  sections: Section[];
}) {
  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-medium tracking-tighter text-zinc-100 leading-none">{title}</h1>
          {description && <p className="text-sm text-zinc-500 mt-2 max-w-[540px] leading-relaxed">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2.5 shrink-0">{actions}</div>}
      </div>
      {sections.map((s, i) => (
        <div key={i}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">{s.title}</h2>
              {s.description && <p className="text-[12px] text-zinc-600 mt-0.5">{s.description}</p>}
            </div>
            {s.actions}
          </div>
          {s.children}
        </div>
      ))}
    </div>
  );
}
