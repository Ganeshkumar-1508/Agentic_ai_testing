import { describe, expect, it } from "vitest";
import type { GraphSummary, KGNode, KnowledgeGraph } from "./types";
import {
  buildNodeHeuristicSummary,
  deriveGraphDisplayMeta,
  graphSummaryDisplayLabel,
  nodeDisplayName,
  nodeSecondaryLabel,
  rankSearchResults,
} from "./view-model";

const baseGraph: KnowledgeGraph = {
  version: "schema v5",
  metadata: {
    repositoryDisplayName: "internal/payments-service",
    branch: "main",
    versionLabel: "schema v5",
    indexedAt: "2026-06-08T10:00:00Z",
    graphId: "graph-123",
  },
  nodes: [
    {
      id: "1",
      type: "class",
      name: "AuthService",
      file: "src/services/auth.ts",
      summary: "",
      tags: ["service", "auth"],
      language: "typescript",
    },
    {
      id: "2",
      type: "function",
      name: "auth/login",
      file: "src/routes/auth.ts",
      summary: "",
      tags: ["route"],
      language: "typescript",
    },
  ],
  edges: [
    { source: "2", target: "1", type: "calls", direction: "forward", weight: 1 },
  ],
};

describe("knowledge graph view-model helpers", () => {
  it("prefers richer backend metadata for display meta", () => {
    const summary: GraphSummary = {
      id: "fallback-graph",
      volume: "fallback-graph",
      node_count: 10,
      edge_count: 20,
      repo_url: "https://github.com/example/fallback.git",
      repository_display_name: "example/fallback",
      branch: "develop",
      version_label: "schema v2",
      indexed_at: "2026-06-01T00:00:00Z",
      language: "codegraph",
    };

    const meta = deriveGraphDisplayMeta(baseGraph, summary);

    expect(meta.repoDisplayName).toBe("internal/payments-service");
    expect(meta.branch).toBe("main");
    expect(meta.versionLabel).toBe("schema v5");
    expect(meta.graphId).toBe("graph-123");
  });

  it("drops weak placeholder graph labels in favor of grounded repository labels", () => {
    const summary: GraphSummary = {
      id: "graph-fallback-7",
      volume: "graph-fallback-7",
      node_count: 10,
      edge_count: 20,
      repo_url: "https://github.com/example/payments.git",
      repository_display_name: "Unnamed graph",
      branch: "develop",
      version_label: "schema v2",
      indexed_at: "2026-06-01T00:00:00Z",
      snapshot_label: "Snapshot",
      language: "codegraph",
    };

    expect(graphSummaryDisplayLabel(summary)).toBe("example/payments");

    const meta = deriveGraphDisplayMeta(
      {
        ...baseGraph,
        metadata: {
          ...baseGraph.metadata,
          repositoryDisplayName: "Unnamed graph",
          snapshotLabel: "Untitled graph",
          repoUrl: "https://github.com/example/payments.git",
        },
      },
      summary
    );

    expect(meta.repoDisplayName).toBe("example/payments");
    expect(meta.snapshotLabel).toBe("graph-fallback-7");
  });

  it("falls back to grounded path context when repository labels are missing", () => {
    const meta = deriveGraphDisplayMeta(
      {
        ...baseGraph,
        metadata: {
          repositoryDisplayName: "Knowledge graph",
          snapshotLabel: "Snapshot",
          graphId: "graph-local-12",
        },
        project: {
          name: "Unnamed graph",
          description: "",
          languages: ["python"],
          frameworks: [],
          analyzedAt: "2026-06-08T10:00:00Z",
          gitCommitHash: "abc123",
        },
        nodes: [
          {
            id: "1",
            type: "file",
            name: "__init__.py",
            file: "Poc/__init__.py",
            summary: "",
            tags: [],
            language: "python",
          },
        ],
        edges: [],
      },
      null
    );

    expect(meta.repoDisplayName).toBe("Poc");
    expect(meta.snapshotLabel).toBe("Poc");
  });

  it("ignores hidden tool directories when deriving path-based graph labels", () => {
    const meta = deriveGraphDisplayMeta(
      {
        ...baseGraph,
        metadata: {
          repositoryDisplayName: "Unnamed graph",
          snapshotLabel: "Untitled graph",
          graphId: "graph-local-22",
        },
        nodes: [
          {
            id: "1",
            type: "file",
            name: "SKILL.md",
            file: ".roo/skills/to-prd/SKILL.md",
            summary: "",
            tags: [],
            language: "markdown",
          },
          {
            id: "2",
            type: "file",
            name: "__init__.py",
            file: "Poc/__init__.py",
            summary: "",
            tags: [],
            language: "python",
          },
          {
            id: "3",
            type: "file",
            name: "agents.py",
            file: "Poc/agents.py",
            summary: "",
            tags: [],
            language: "python",
          },
        ],
        edges: [],
      },
      null
    );

    expect(meta.repoDisplayName).toBe("Poc");
    expect(meta.snapshotLabel).toBe("Poc");
  });

  it("prefers repository url over graph-like snapshot labels in graph summaries", () => {
    const summary: GraphSummary = {
      id: "graph-xyz-9",
      volume: "graph-xyz-9",
      node_count: 12,
      edge_count: 18,
      repo_url: "https://github.com/example-org/payments-service.git",
      repository_display_name: null,
      branch: null,
      version_label: null,
      indexed_at: null,
      snapshot_label: "graph-xyz-9",
      language: "codegraph",
    };

    expect(graphSummaryDisplayLabel(summary)).toBe("example-org/payments-service");
  });

  it("ranks exact and prefix search hits ahead of looser matches", () => {
    const results = rankSearchResults(baseGraph, new Set(["1", "2"]), "auth", 10);

    expect(results).toHaveLength(2);
    expect(results[0]?.node.name).toBe("AuthService");
    expect(results[1]?.node.name).toBe("auth/login");
  });

  it("builds a heuristic summary when backend summary is absent", () => {
    const summary = buildNodeHeuristicSummary(baseGraph.nodes[0], 1, 0);

    expect(summary).toContain("AuthService");
    expect(summary).toContain("src/services/auth.ts");
    expect(summary).toContain("Primary language: typescript");
  });

  it("promotes contextual file labels for generic file nodes", () => {
    const genericFileNode: KGNode = {
      id: "3",
      type: "file",
      name: "__init__.py",
      file: "Poc/__init__.py",
      summary: "",
      tags: [],
      language: "python",
    };

    expect(nodeDisplayName(genericFileNode)).toBe("Poc/__init__.py");
    expect(nodeSecondaryLabel(genericFileNode)).toBe("python");
  });
});
