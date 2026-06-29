import MiniSearch from "minisearch";
import type { KGNode } from "@/lib/types/kg";

export interface KGSearchDoc {
  id: string;
  name: string;
  summary: string;
  file: string;
  tags: string;
  language: string;
  type: string;
}

const FIELDS = ["name", "summary", "file", "tags", "language", "type"];

export const KG_SEARCH_OPTIONS = {
  fields: FIELDS,
  storeFields: ["name", "type", "file", "language"],
  searchOptions: {
    boost: { name: 3, file: 2, tags: 1.5, summary: 1 } as Record<string, number>,
    fuzzy: 0.2,
    prefix: true,
    combineWith: "AND" as const,
  },
};

export function toKGSearchDoc(n: KGNode): KGSearchDoc {
  return {
    id: n.id,
    name: n.name,
    summary: n.summary,
    file: n.file ?? n.filePath ?? "",
    tags: (n.tags ?? []).join(" "),
    language: n.language ?? "",
    type: n.type,
  };
}

export function buildKGSearchIndex(nodes: KGNode[]): MiniSearch<KGSearchDoc> {
  const index = new MiniSearch<KGSearchDoc>(KG_SEARCH_OPTIONS);
  index.addAll(nodes.map(toKGSearchDoc));
  return index;
}

export function searchKGIndex(
  index: MiniSearch<KGSearchDoc>,
  query: string
): Set<string> {
  const q = query.trim();
  if (!q) return new Set();
  const results = index.search(q);
  return new Set(results.map((r) => r.id));
}

export function searchStats(
  index: MiniSearch<KGSearchDoc>,
  query: string
): { matched: number; timeMs: number; terms: number } {
  const q = query.trim();
  if (!q) return { matched: 0, timeMs: 0, terms: 0 };
  const t0 = performance.now();
  const results = index.search(q);
  const timeMs = performance.now() - t0;
  return {
    matched: results.length,
    timeMs,
    terms: q.split(/\s+/).filter(Boolean).length,
  };
}
