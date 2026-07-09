"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, Settings2, Code, Terminal, Repeat, Layers, Archive, Bell, GitBranch, Cpu } from "lucide-react";

export interface AdvancedConfig {
  parallelism: number;
  shard_count: number;
  retry_on_failure: boolean;
  max_retries: number;
  fail_fast: boolean;
  continue_on_failure: boolean;
  cache_key: string;
  cache_directories: string[];
  artifact_paths: string[];
  notification_channels: string[];
  pre_commands: string[];
  post_commands: string[];
  timeout_seconds: number;
  os: string;
  runtime_version: string;
  browser: string;
  auto_commit: boolean;
  commit_branch: string;
  tags: string[];
}

interface Props {
  config: AdvancedConfig;
  onChange: (config: AdvancedConfig) => void;
}

const TABS = [
  { id: "execution", label: "Execution", icon: Cpu },
  { id: "instructions", label: "Instructions", icon: Terminal },
  { id: "parallelism", label: "Parallelism", icon: Layers },
  { id: "retry", label: "Retry", icon: Repeat },
  { id: "caching", label: "Caching", icon: Archive },
  { id: "artifacts", label: "Artifacts", icon: FolderIcon },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "versioning", label: "Versioning", icon: GitBranch },
];

function FolderIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
  );
}

const DEFAULT_CONFIG: AdvancedConfig = {
  parallelism: 1,
  shard_count: 1,
  retry_on_failure: true,
  max_retries: 2,
  fail_fast: false,
  continue_on_failure: true,
  cache_key: "",
  cache_directories: [],
  artifact_paths: [],
  notification_channels: [],
  pre_commands: [],
  post_commands: [],
  timeout_seconds: 1800,
  os: "linux",
  runtime_version: "",
  browser: "",
  auto_commit: false,
  commit_branch: "",
  tags: [],
};

export { DEFAULT_CONFIG };

export function AdvancedPipelineConfig({ config, onChange }: Props) {
  const [expanded, setExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState("execution");

  const update = (partial: Partial<AdvancedConfig>) => onChange({ ...config, ...partial });

  const toggleArrayItem = (key: "cache_directories" | "artifact_paths" | "notification_channels" | "pre_commands" | "post_commands" | "tags", value: string) => {
    const arr = [...config[key]];
    const idx = arr.indexOf(value);
    if (idx >= 0) arr.splice(idx, 1);
    else arr.push(value);
    update({ [key]: arr });
  };

  const yamlPreview = `pipeline:
  parallelism: ${config.parallelism}
  shards: ${config.shard_count}
  retry:
    enabled: ${config.retry_on_failure}
    max_retries: ${config.max_retries}
  fail_fast: ${config.fail_fast}
  continue_on_failure: ${config.continue_on_failure}
  timeout: ${config.timeout_seconds}s
${config.cache_key ? `  cache_key: ${config.cache_key}` : ""}
${config.os ? `  os: ${config.os}` : ""}
${config.runtime_version ? `  runtime_version: ${config.runtime_version}` : ""}
${config.browser ? `  browser: ${config.browser}` : ""}
${config.auto_commit ? `  auto_commit:
    enabled: true
    branch: ${config.commit_branch || "main"}` : ""}
${config.tags.length ? `  tags: [${config.tags.join(", ")}]` : ""}`;

  return (
    <div className="border border-white/[0.05] rounded-[1.5rem] bg-surface overflow-hidden shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <button onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full px-4 py-3 text-xs text-neutral-400 hover:text-neutral-200 transition-colors">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-white/[0.03] flex items-center justify-center">
            <Settings2 size={12} strokeWidth={1.5} className="text-neutral-500" />
          </div>
          <span className="font-medium text-neutral-300">Advanced Configuration</span>
          <span className="text-[10px] text-zinc-600 font-mono">Quick</span>
        </div>
        <motion.div animate={{ rotate: expanded ? 0 : -90 }} transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}>
          <ChevronDown size={12} strokeWidth={1.5} className="text-neutral-500" />
        </motion.div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }} className="overflow-hidden border-t border-white/[0.05]">
            <div className="flex gap-0">
              {/* Tab navigation */}
              <div className="w-36 shrink-0 border-r border-white/[0.05] p-2 space-y-0.5">
                {TABS.map((tab) => {
                  const TabIcon = tab.icon;
                  return (
                    <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                      className={`flex items-center gap-2 w-full px-2.5 py-1.5 rounded-lg text-[10px] transition-colors ${
                        activeTab === tab.id ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.03]"
                      }`}>
                      <TabIcon className="w-3 h-3" strokeWidth={1.5} />
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* Tab content */}
              <div className="flex-1 p-4 space-y-3 min-h-[260px]">
                <AnimatePresence mode="wait">
                  <motion.div key={activeTab} initial={{ opacity: 0, x: 4 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -4 }}
                    transition={{ duration: 0.15 }}>
                    {activeTab === "execution" && (
                      <div className="space-y-3">
                        <Field label="Timeout (seconds)">
                          <input type="number" value={config.timeout_seconds} onChange={(e) => update({ timeout_seconds: parseInt(e.target.value) || 1800 })}
                            className="w-24 bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40 font-mono" />
                        </Field>
                        <Field label="OS">
                          <select value={config.os} onChange={(e) => update({ os: e.target.value })}
                            className="bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40">
                            <option value="linux">Linux</option>
                            <option value="windows">Windows</option>
                            <option value="macos">macOS</option>
                          </select>
                        </Field>
                        <Field label="Runtime Version">
                          <input value={config.runtime_version} onChange={(e) => update({ runtime_version: e.target.value })}
                            placeholder="e.g. 18.x, 3.11"
                            className="w-40 bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 font-mono" />
                        </Field>
                        <Field label="Browser">
                          <select value={config.browser} onChange={(e) => update({ browser: e.target.value })}
                            className="bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40">
                            <option value="">None</option>
                            <option value="chromium">Chromium</option>
                            <option value="firefox">Firefox</option>
                            <option value="webkit">WebKit</option>
                          </select>
                        </Field>
                      </div>
                    )}
                    {activeTab === "instructions" && (
                      <div className="space-y-3">
                        <Field label="Pre-commands (one per line)">
                          <textarea value={config.pre_commands.join("\n")} onChange={(e) => update({ pre_commands: e.target.value.split("\n").filter(Boolean) })}
                            rows={3} placeholder="npm install&#10;pip install -r requirements.txt"
                            className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 font-mono resize-none" />
                        </Field>
                        <Field label="Post-commands (one per line)">
                          <textarea value={config.post_commands.join("\n")} onChange={(e) => update({ post_commands: e.target.value.split("\n").filter(Boolean) })}
                            rows={3} placeholder="npm run report&#10;cp coverage/lcov.info ./artifacts/"
                            className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 font-mono resize-none" />
                        </Field>
                      </div>
                    )}
                    {activeTab === "parallelism" && (
                      <div className="space-y-3">
                        <Field label="Parallelism (containers)">
                          <input type="number" min={1} max={16} value={config.parallelism} onChange={(e) => update({ parallelism: parseInt(e.target.value) || 1 })}
                            className="w-20 bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40 font-mono" />
                        </Field>
                        <Field label="Shard Count">
                          <input type="number" min={1} max={32} value={config.shard_count} onChange={(e) => update({ shard_count: parseInt(e.target.value) || 1 })}
                            className="w-20 bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40 font-mono" />
                        </Field>
                      </div>
                    )}
                    {activeTab === "retry" && (
                      <div className="space-y-3">
                        <Toggle label="Retry on Failure" checked={config.retry_on_failure} onChange={(v) => update({ retry_on_failure: v })} />
                        {config.retry_on_failure && (
                          <Field label="Max Retries">
                            <input type="number" min={1} max={10} value={config.max_retries} onChange={(e) => update({ max_retries: parseInt(e.target.value) || 2 })}
                              className="w-20 bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40 font-mono" />
                          </Field>
                        )}
                        <Toggle label="Fail Fast" checked={config.fail_fast} onChange={(v) => update({ fail_fast: v })} />
                        <Toggle label="Continue on Failure" checked={config.continue_on_failure} onChange={(v) => update({ continue_on_failure: v })} />
                      </div>
                    )}
                    {activeTab === "caching" && (
                      <div className="space-y-3">
                        <Field label="Cache Key">
                          <input value={config.cache_key} onChange={(e) => update({ cache_key: e.target.value })}
                            placeholder="e.g. deps-{{ checksum 'package-lock.json' }}"
                            className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 font-mono" />
                        </Field>
                        <ArrayInput label="Cache Directories" items={config.cache_directories} onAdd={(v) => toggleArrayItem("cache_directories", v)} onRemove={(v) => toggleArrayItem("cache_directories", v)}
                          placeholder="node_modules" />
                      </div>
                    )}
                    {activeTab === "artifacts" && (
                      <div className="space-y-3">
                        <ArrayInput label="Artifact Paths" items={config.artifact_paths} onAdd={(v) => toggleArrayItem("artifact_paths", v)} onRemove={(v) => toggleArrayItem("artifact_paths", v)}
                          placeholder="coverage/" />
                      </div>
                    )}
                    {activeTab === "notifications" && (
                      <div className="space-y-3">
                        <ArrayInput label="Notification Channels" items={config.notification_channels} onAdd={(v) => toggleArrayItem("notification_channels", v)} onRemove={(v) => toggleArrayItem("notification_channels", v)}
                          placeholder="slack:#alerts" />
                      </div>
                    )}
                    {activeTab === "versioning" && (
                      <div className="space-y-3">
                        <Toggle label="Auto-Commit Tests" checked={config.auto_commit} onChange={(v) => update({ auto_commit: v })} />
                        {config.auto_commit && (
                          <Field label="Commit Branch">
                            <input value={config.commit_branch} onChange={(e) => update({ commit_branch: e.target.value })}
                              placeholder="main"
                              className="w-40 bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 font-mono" />
                          </Field>
                        )}
                        <ArrayInput label="Tags" items={config.tags} onAdd={(v) => toggleArrayItem("tags", v)} onRemove={(v) => toggleArrayItem("tags", v)}
                          placeholder="regression" />
                      </div>
                    )}
                  </motion.div>
                </AnimatePresence>
              </div>

              {/* YAML Preview */}
              <div className="w-56 shrink-0 border-l border-white/[0.05] p-3 bg-white/[0.01]">
                <div className="flex items-center gap-1.5 mb-2">
                  <Code className="w-3 h-3 text-zinc-500" strokeWidth={1.5} />
                  <span className="text-[9px] font-medium text-zinc-600 uppercase tracking-wider">YAML Preview</span>
                </div>
                <pre className="text-[9px] text-zinc-500 font-mono leading-relaxed whitespace-pre-wrap">{yamlPreview}</pre>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-zinc-500 font-medium">{label}</span>
      {children}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!checked)} className="flex items-center justify-between w-full py-1">
      <span className="text-[10px] text-zinc-500 font-medium">{label}</span>
      <div className={`w-8 h-4 rounded-full transition-colors ${checked ? "bg-emerald-500" : "bg-zinc-700"}`}>
        <div className={`w-3 h-3 rounded-full bg-white mt-0.5 transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
      </div>
    </button>
  );
}

function ArrayInput({ label, items, onAdd, onRemove, placeholder }: { label: string; items: string[]; onAdd: (v: string) => void; onRemove: (v: string) => void; placeholder: string }) {
  const [input, setInput] = useState("");
  return (
    <div className="space-y-1.5">
      <span className="text-[10px] text-zinc-500 font-medium">{label}</span>
      <div className="flex flex-wrap gap-1">
        {items.map((item) => (
          <span key={item} className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/[0.04] text-[9px] text-zinc-400 font-mono">
            {item}
            <button onClick={() => onRemove(item)} className="text-zinc-700 hover:text-red-400">&times;</button>
          </span>
        ))}
      </div>
      <div className="flex gap-1">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={placeholder}
          onKeyDown={(e) => { if (e.key === "Enter" && input.trim()) { onAdd(input.trim()); setInput(""); } }}
          className="flex-1 bg-white/[0.04] border border-white/[0.06] rounded-lg px-2 py-1 text-[10px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 font-mono" />
      </div>
    </div>
  );
}
