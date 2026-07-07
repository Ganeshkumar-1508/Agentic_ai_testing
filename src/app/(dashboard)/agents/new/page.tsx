"use client";

import { useCallback, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Bot, Check, Save, User, Wrench, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { checkAgentName, createAgent, getAgent } from "@/lib/api/agents";
import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

const NAME_RE = /^[A-Za-z0-9-]+$/;

type Step = "name" | "tools" | "prompt" | "confirm";

const TOOL_PRESETS = [
  {
    id: "general",
    label: "General Purpose",
    desc: "Read, write, search, and execute. Best for most tasks.",
    icon: "G",
    tools: ["codegraph_explore", "codegraph_search", "glob", "grep", "read_file", "write_file", "edit_file", "bash", "web_fetch", "memory"],
  },
  {
    id: "code-expert",
    label: "Code Architect",
    desc: "Deep code analysis. Read-only, no mutations.",
    icon: "A",
    tools: ["codegraph_explore", "codegraph_search", "codegraph_node", "codegraph_callers", "codegraph_callees", "lsp", "semantic_search", "glob", "grep", "read_file"],
  },
  {
    id: "researcher",
    label: "Researcher",
    desc: "Web research and content extraction. Read-only.",
    icon: "R",
    tools: ["web_search", "web_fetch", "web_extract", "memory", "read_file", "grep"],
  },
  {
    id: "data-analyst",
    label: "Data Analyst",
    desc: "Run code, query databases, analyze data.",
    icon: "D",
    tools: ["bash", "execute_code", "database_query", "glob", "grep", "read_file", "write_file", "web_fetch"],
  },
  {
    id: "devops",
    label: "DevOps / SRE",
    desc: "Infrastructure automation, Docker, shell scripts.",
    icon: "O",
    tools: ["bash", "glob", "grep", "read_file", "write_file", "edit_file", "web_fetch", "memory"],
  },
  {
    id: "writer",
    label: "Documentation Writer",
    desc: "Read codebases, write markdown and documentation.",
    icon: "W",
    tools: ["read_file", "write_file", "glob", "grep", "codegraph_search", "web_fetch", "memory"],
  },
];

export default function NewAgentPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("name");
  const [nameInput, setNameInput] = useState("");
  const [descInput, setDescInput] = useState("");
  const [promptInput, setPromptInput] = useState("");
  const [selectedPreset, setSelectedPreset] = useState(TOOL_PRESETS[0].id);
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [availableSkills, setAvailableSkills] = useState<string[]>([]);
  const [nameError, setNameError] = useState("");
  const [isChecking, setIsChecking] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const handleConfirmName = useCallback(async () => {
    const trimmed = nameInput.trim();
    if (!trimmed) return;
    if (!NAME_RE.test(trimmed)) {
      setNameError("Use only letters, numbers, and hyphens");
      return;
    }

    setNameError("");
    setIsChecking(true);
    try {
      const result = await checkAgentName(trimmed);
      if (!result.available) {
        setNameError("An agent with this name already exists");
        return;
      }
    } catch {
      setNameError("Could not verify name availability");
      return;
    } finally {
      setIsChecking(false);
    }

    setStep("tools");
  }, [nameInput]);

  useEffect(() => {
    api.get<any[]>("/api/settings/providers").then((data) => {
      if (Array.isArray(data)) {
        setAvailableModels(data.filter((p: any) => p.enabled !== false).map((p: any) => p.model || p.provider || "").filter(Boolean));
      }
    }).catch(() => {});
    api.get<{ skills?: { name: string }[] }>("/api/skills").then((data) => {
      if (data?.skills) setAvailableSkills(data.skills.map((s: any) => s.name).filter(Boolean));
    }).catch(() => {});
  }, []);

  const handleSave = useCallback(async () => {
    const name = nameInput.trim();
    const prompt = promptInput.trim();
    const desc = descInput.trim() || `Custom agent: ${name}`;
    if (!name || !prompt) return;

    const preset = TOOL_PRESETS.find(p => p.id === selectedPreset);
    const tools = preset?.tools ?? TOOL_PRESETS[0].tools;

    setIsSaving(true);
    try {
      await createAgent({
        name,
        prompt,
        description: desc,
        tools,
        model: selectedModel || null,
        skills: selectedSkills,
      });
      toast.success(`Agent "${name}" created`);
      router.push("/agents");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save agent");
    } finally {
      setIsSaving(false);
    }
  }, [nameInput, promptInput, descInput, selectedPreset, router]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      {step === "name" && (
        <>
          <div className="flex items-center gap-3 mb-8">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-zinc-800/50 bg-zinc-900/50">
              <Bot size={18} strokeWidth={1.5} className="text-emerald-400" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-neutral-100 tracking-tight">Create Agent</h1>
              <p className="text-xs text-neutral-500">Give your agent a name to get started</p>
            </div>
          </div>

          <div className="space-y-3">
            <label className="text-xs font-medium text-neutral-400">Agent Name</label>
            <input
              type="text"
              value={nameInput}
              onChange={(e) => { setNameInput(e.target.value); setNameError(""); }}
              onKeyDown={(e) => e.key === "Enter" && handleConfirmName()}
              placeholder="e.g. rust-expert"
              className="w-full rounded-lg border border-zinc-800/50 bg-zinc-900/60 px-3.5 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              autoFocus
            />
            {nameError && <p className="text-xs text-red-400">{nameError}</p>}
            <p className="text-[11px] text-neutral-600">Lowercase letters, numbers, and hyphens only</p>
          </div>

          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={handleConfirmName}
              disabled={!nameInput.trim() || isChecking}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/90 px-4 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40 active:scale-[0.97] transition-all"
            >
              {isChecking ? "Checking..." : "Continue"}
              <ArrowLeft size={12} strokeWidth={2} className="rotate-180" />
            </button>
            <button
              onClick={() => router.push("/agents")}
              className="rounded-lg border border-zinc-800/50 px-4 py-2 text-xs text-neutral-500 hover:text-neutral-300 transition-colors active:scale-[0.97]"
            >
              Cancel
            </button>
          </div>
        </>
      )}

      {step === "tools" && (
        <>
          <div className="flex items-center gap-3 mb-8">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-zinc-800/50 bg-zinc-900/50">
              <Wrench size={18} strokeWidth={1.5} className="text-emerald-400" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-neutral-100 tracking-tight">
                Configure <span className="text-emerald-400">{nameInput}</span>
              </h1>
              <p className="text-xs text-neutral-500">Choose a capability preset and describe your agent</p>
            </div>
          </div>

          <div className="space-y-4">
            <label className="text-xs font-medium text-neutral-400">Capability Preset</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {TOOL_PRESETS.map((preset) => {
                const active = selectedPreset === preset.id;
                return (
                  <button
                    key={preset.id}
                    onClick={() => setSelectedPreset(preset.id)}
                    className={cn(
                      "flex items-start gap-3 rounded-xl border p-3.5 text-left transition-all duration-200 active:scale-[0.98]",
                      active
                        ? "border-emerald-500/40 bg-emerald-500/5 shadow-[inset_0_0_0_1px_rgba(52,211,153,0.15)]"
                        : "border-zinc-800/50 bg-zinc-900/40 hover:border-zinc-700/50"
                    )}
                  >
                    <div className={cn(
                      "w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold shrink-0",
                      active ? "bg-emerald-500/15 text-emerald-400" : "bg-zinc-800/50 text-zinc-500"
                    )}>
                      {preset.icon}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-zinc-200">{preset.label}</div>
                      <div className="text-[11px] text-zinc-600 mt-0.5 line-clamp-2">{preset.desc}</div>
                      <div className="text-[10px] text-zinc-700 mt-1 font-mono">{preset.tools.length} tools</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-6 space-y-3">
            <label className="text-xs font-medium text-neutral-400">Description</label>
            <input
              type="text"
              value={descInput}
              onChange={(e) => setDescInput(e.target.value)}
              placeholder={`Custom agent: ${nameInput}`}
              className="w-full rounded-lg border border-zinc-800/50 bg-zinc-900/60 px-3.5 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
            />
            <p className="text-[11px] text-neutral-600">A short description shown in the agent list</p>
          </div>

          <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-3">
              <label className="text-xs font-medium text-neutral-400">Model (optional)</label>
              <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full rounded-lg border border-zinc-800/50 bg-zinc-900/60 px-3.5 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
              >
                <option value="">System default</option>
                {availableModels.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <p className="text-[11px] text-neutral-600">Override the default model for this agent</p>
            </div>
            <div className="space-y-3">
              <label className="text-xs font-medium text-neutral-400">Skills (optional)</label>
              <div className="max-h-32 overflow-y-auto rounded-lg border border-zinc-800/50 bg-zinc-900/60 p-2 space-y-1">
                {availableSkills.length === 0 ? (
                  <p className="text-[11px] text-neutral-600 text-center py-2">No skills available</p>
                ) : (
                  availableSkills.map((s) => (
                    <label key={s} className="flex items-center gap-2 cursor-pointer px-2 py-1 rounded hover:bg-zinc-800/40 transition-colors">
                      <input type="checkbox" checked={selectedSkills.includes(s)} onChange={(e) => setSelectedSkills(e.target.checked ? [...selectedSkills, s] : selectedSkills.filter(x => x !== s))}
                        className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/20" />
                      <span className="text-xs text-zinc-300">{s}</span>
                    </label>
                  ))
                )}
              </div>
              <p className="text-[11px] text-neutral-600">Load specific skills for this agent</p>
            </div>
          </div>

          <div className="mt-8 flex items-center gap-3">
            <button
              onClick={() => setStep("prompt")}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/90 px-4 py-2 text-xs font-medium text-white hover:bg-emerald-500 active:scale-[0.97] transition-all"
            >
              Continue to Prompt
              <ArrowLeft size={12} strokeWidth={2} className="rotate-180" />
            </button>
            <button
              onClick={() => setStep("name")}
              className="rounded-lg border border-zinc-800/50 px-4 py-2 text-xs text-neutral-500 hover:text-neutral-300 transition-colors active:scale-[0.97]"
            >
              Back
            </button>
          </div>
        </>
      )}

      {step === "prompt" && (
        <>
          <div className="flex items-center gap-3 mb-8">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-zinc-800/50 bg-zinc-900/50">
              <User size={18} strokeWidth={1.5} className="text-emerald-400" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-neutral-100 tracking-tight">
                Define <span className="text-emerald-400">{nameInput}</span>
              </h1>
              <p className="text-xs text-neutral-500">Describe what this agent should do and how it should behave</p>
            </div>
          </div>

          <div className="space-y-3">
            <label className="text-xs font-medium text-neutral-400">System Prompt</label>
            <textarea
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              placeholder={`**Identity**

{name} — your specialist for {domain}. Goal: {purpose}.

**Core Traits**

- {trait 1 — behavioral rule}
- {trait 2 — behavioral rule}
- {trait 3 — behavioral rule}

**Communication**

{ tone, default language, style notes }`}
              className="min-h-[320px] w-full rounded-lg border border-zinc-800/50 bg-zinc-900/60 px-3.5 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-700 font-mono focus:border-emerald-500/40 focus:outline-none resize-y"
              autoFocus
            />
            <p className="text-[11px] text-neutral-600">
              Use markdown with sections: Identity, Core Traits, Communication. Under 300 words recommended.
            </p>
          </div>

          {promptInput.trim() && (
            <div className="mt-6 rounded-xl border border-zinc-800/30 bg-zinc-900/30 p-4">
              <p className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider mb-2">Preview</p>
              <div className="prose prose-invert prose-sm max-w-none">
                <MarkdownRenderer content={promptInput.replace(/\{name\}/g, nameInput)} />
              </div>
            </div>
          )}

          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={!promptInput.trim() || isSaving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/90 px-4 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40 active:scale-[0.97] transition-all"
            >
              {isSaving ? (
                "Saving..."
              ) : (
                <><Save size={12} strokeWidth={2} /> Save Agent</>
              )}
            </button>
            <button
              onClick={() => setStep("tools")}
              className="rounded-lg border border-zinc-800/50 px-4 py-2 text-xs text-neutral-500 hover:text-neutral-300 transition-colors active:scale-[0.97]"
            >
              Back
            </button>
          </div>
        </>
      )}
    </div>
  );
}
