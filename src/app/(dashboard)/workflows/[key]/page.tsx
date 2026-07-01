"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Connection,
  addEdge,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  type NodeTypes,
  type DefaultEdgeOptions,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api/api-client";
import { motion } from "framer-motion";
import { Loader2, Save, Play, Clock, ArrowLeft, Plus, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentTaskNode } from "@/components/workflow/nodes/AgentTaskNode";
import { HumanInputNode } from "@/components/workflow/nodes/HumanInputNode";
import { RouterNode } from "@/components/workflow/nodes/RouterNode";

const nodeTypes: NodeTypes = {
  agent: AgentTaskNode,
  human_input: HumanInputNode,
  router: RouterNode,
};

const defaultEdgeOptions: DefaultEdgeOptions = {
  style: { stroke: "#52525b", strokeWidth: 1.5 },
  type: "smoothstep",
};

function workflowToNodesAndEdges(wf: any): { nodes: Node[]; edges: Edge[] } {
  const VALID_TYPES = new Set(["agent", "human_input", "router"]);
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const steps = wf?.steps ?? [];

  nodes.push({
    id: "start",
    type: "input",
    position: { x: 250, y: 0 },
    data: { label: "Start" },
    style: {
      background: "#059669",
      color: "white",
      border: "none",
      borderRadius: "999px",
      padding: "8px 20px",
      fontSize: "12px",
      fontWeight: 600,
    },
  });

  steps.forEach((step: any, i: number) => {
    const x = 200 + (i % 2) * 180;
    const y = 100 + Math.floor(i / 2) * 140;
    const nodeType = VALID_TYPES.has(step.type) ? step.type : "agent";
    nodes.push({
      id: step.id,
      type: nodeType,
      position: { x, y },
      data: {
        label: step.label || step.id,
        prompt: step.prompt || "",
        config: step.config || {},
        branch_rules: step.branch_rules || [],
        children: step.children || [],
      },
    });

    const prevId = i === 0 ? "start" : steps[i - 1]?.id || "start";
    if (prevId !== step.id) {
      edges.push({
        id: `e-${prevId}-${step.id}`,
        source: prevId,
        target: step.id,
        style: step.mode === "parallel"
          ? { stroke: "#8b5cf6", strokeWidth: 2 }
          : step.mode === "conditional"
            ? { stroke: "#d97706", strokeWidth: 1.5, strokeDasharray: "5 5" }
            : { stroke: "#52525b", strokeWidth: 1.5 },
        label: step.mode !== "sequential" ? step.mode : undefined,
      });
    }
  });

  nodes.push({
    id: "end",
    type: "output",
    position: { x: 250, y: 100 + Math.floor(steps.length / 2) * 140 + 60 },
    data: { label: "End" },
    style: {
      background: "#52525b",
      color: "white",
      border: "none",
      borderRadius: "999px",
      padding: "8px 20px",
      fontSize: "12px",
      fontWeight: 600,
    },
  });

  const lastStep = steps[steps.length - 1];
  if (lastStep) {
    edges.push({
      id: `e-${lastStep.id}-end`,
      source: lastStep.id,
      target: "end",
    });
  }

  return { nodes, edges };
}

function nodesAndEdgesToWorkflow(key: string, title: string, nodes: Node[], edges: Edge[]) {
  const stepNodes = nodes.filter((n) => n.id !== "start" && n.id !== "end");
  const steps = stepNodes.map((node) => {
    const incomingEdges = edges.filter((e) => e.target === node.id);
    const outgoingEdges = edges.filter((e) => e.source === node.id);
    const depEdge = incomingEdges.find((e) => e.source !== "start");
    const mode = depEdge?.label === "parallel" ? "parallel" : depEdge?.label === "conditional" ? "conditional" : "sequential";

    return {
      id: node.id,
      label: node.data?.label || node.id,
      type: node.type === "human_input" ? "human_input" : node.type === "router" ? "router" : "agent",
      prompt: node.data?.prompt || "",
      mode,
      depends_on: depEdge ? [depEdge.source] : [],
      config: node.data?.config || { model: null, toolsets: ["read"], timeout_sec: 300, role: "leaf" },
      branch_rules: node.data?.branch_rules || [],
      children: node.data?.children || [],
    };
  });

  return {
    key,
    title,
    description: "",
    category: "Workflow",
    steps,
    tags: [],
    schedule_template: "",
  };
}

function WorkflowEditor({ workflowKey }: { workflowKey: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [hasChanges, setHasChanges] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["workflow", workflowKey],
    queryFn: async () => {
      const res = await api.get<{ workflow: any }>(`/api/workflows/${workflowKey}`);
      return res?.workflow;
    },
  });

  useEffect(() => {
    if (data) {
      setTitle(data.title || workflowKey);
      const { nodes: n, edges: e } = workflowToNodesAndEdges(data);
      setNodes(n);
      setEdges(e);
      setHasChanges(false);
    }
  }, [data, workflowKey, setNodes, setEdges]);

  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) => addEdge(params, eds));
      setHasChanges(true);
    },
    [setEdges],
  );

  const onNodesChangeHandler = useCallback(
    (changes: any) => {
      onNodesChange(changes);
      setHasChanges(true);
    },
    [onNodesChange],
  );

  const onEdgesChangeHandler = useCallback(
    (changes: any) => {
      onEdgesChange(changes);
      setHasChanges(true);
    },
    [onEdgesChange],
  );

  const addStep = useCallback((type: string) => {
    const id = `step-${Date.now()}`;
    const existing = nodes.filter((n) => n.id !== "start" && n.id !== "end");
    const y = 100 + Math.floor(existing.length / 2) * 140;
    const x = 200 + (existing.length % 2) * 180;
    const newNode: Node = {
      id,
      type: type === "human_input" ? "human_input" : type === "router" ? "router" : "agent",
      position: { x, y },
      data: {
        label: type === "human_input" ? "Human Input" : type === "router" ? "Router" : "Agent Task",
        prompt: "",
        config: { model: null, toolsets: ["read"], timeout_sec: 300, role: "leaf" },
        branch_rules: [],
        children: [],
      },
    };
    setNodes((nds) => {
      const last = [...nds.filter((n) => n.id !== "end")].pop();
      const newEdges: Edge[] = [];
      if (last && last.id !== "start") {
        newEdges.push({
          id: `e-${last.id}-${id}`,
          source: last.id,
          target: id,
        });
      } else {
        newEdges.push({
          id: `e-start-${id}`,
          source: "start",
          target: id,
        });
      }
      setEdges((eds) => [...eds, ...newEdges]);
      return [...nds.filter((n) => n.id !== "end"), newNode, nds.find((n) => n.id === "end")!];
    });
    setHasChanges(true);
  }, [nodes, setNodes, setEdges]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = nodesAndEdgesToWorkflow(workflowKey, title, nodes, edges);
      return api.put(`/api/workflows/${workflowKey}`, body);
    },
    onSuccess: () => {
      setHasChanges(false);
      queryClient.invalidateQueries({ queryKey: ["workflow", workflowKey] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => api.post(`/api/workflows/${workflowKey}/run`, {}),
  });

  return (
    <div className="h-[calc(100vh-48px)] flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-zinc-800/40 bg-zinc-950/80">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/workflows")}
            className="w-7 h-7 rounded-lg bg-zinc-800/40 flex items-center justify-center text-zinc-500 hover:text-zinc-300 transition-colors">
            <ArrowLeft size={13} strokeWidth={1.5} />
          </button>
          <button onClick={() => router.push(`/workflows/executions?workflow=${workflowKey}`)}
            className="w-7 h-7 rounded-lg bg-zinc-800/40 flex items-center justify-center text-zinc-500 hover:text-zinc-300 transition-colors"
            title="Execution history">
            <History size={13} strokeWidth={1.5} />
          </button>
          <input value={title} onChange={(e) => { setTitle(e.target.value); setHasChanges(true); }}
            className="bg-transparent text-sm font-medium text-zinc-200 outline-none border-b border-transparent focus:border-emerald-500/40 px-1" />
          <span className="text-[10px] font-mono text-zinc-600">{workflowKey}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 mr-2 border-r border-zinc-800/40 pr-2">
            <button onClick={() => addStep("agent")}
              className="text-[10px] px-2 py-1 rounded-md bg-zinc-800/40 text-zinc-400 hover:text-zinc-200 border border-zinc-700/30 transition-all active:scale-[0.97] flex items-center gap-1">
              <Plus size={10} strokeWidth={1.5} /> Agent
            </button>
            <button onClick={() => addStep("human_input")}
              className="text-[10px] px-2 py-1 rounded-md bg-zinc-800/40 text-zinc-400 hover:text-zinc-200 border border-zinc-700/30 transition-all active:scale-[0.97] flex items-center gap-1">
              <Plus size={10} strokeWidth={1.5} /> Human
            </button>
            <button onClick={() => addStep("router")}
              className="text-[10px] px-2 py-1 rounded-md bg-zinc-800/40 text-zinc-400 hover:text-zinc-200 border border-zinc-700/30 transition-all active:scale-[0.97] flex items-center gap-1">
              <Plus size={10} strokeWidth={1.5} /> Router
            </button>
          </div>

          <button onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs hover:bg-emerald-500/20 transition-all active:scale-[0.97] disabled:opacity-40">
            {runMutation.isPending ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} strokeWidth={1.5} />}
            Run
          </button>
          <button onClick={() => saveMutation.mutate()}
            disabled={!hasChanges || saveMutation.isPending}
            className={cn("inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs transition-all active:scale-[0.97]",
              hasChanges
                ? "bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                : "bg-zinc-800/30 text-zinc-600 cursor-not-allowed")}>
            {saveMutation.isPending ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} strokeWidth={1.5} />}
            Save
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 bg-zinc-950">
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-zinc-600">
            <Loader2 size={20} className="animate-spin" strokeWidth={2} />
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChangeHandler}
            onEdgesChange={onEdgesChangeHandler}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            fitView
            colorMode="dark"
          >
            <Background color="#27272a" gap={20} />
            <Controls className="bg-zinc-900 border-zinc-800 [&_button]:text-zinc-400 [&_button]:hover:bg-zinc-800 [&_button]:border-zinc-700" />
            <MiniMap
              className="bg-zinc-900 border-zinc-800"
              nodeColor="#3b82f6"
              maskColor="rgba(0,0,0,0.7)"
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}

export default function WorkflowDetailPage() {
  const params = useParams();
  const key = params?.key as string;

  return (
    <ReactFlowProvider>
      <WorkflowEditor workflowKey={key} />
    </ReactFlowProvider>
  );
}
