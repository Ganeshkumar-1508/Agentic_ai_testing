"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { cn } from "@/lib/utils";
import {
  Key,
  Plus,
  Trash2,
  Check,
  Copy,
  Globe,
  Github,
  ExternalLink,
  ChevronDown,
  Terminal,
  Loader2,
} from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { api } from "@/lib/api/api-client";

interface ApiKey {
  id: string;
  name: string;
  enabled: boolean;
  createdAt: string;
}

const D = "$";
const GHA = "name: TestAI\non: pull_request\njobs:\n  testai:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - name: Run TestAI\n        run: |\n          curl -X POST " + D + "{{ secrets.TESTAI_BACKEND }}/api/ci/run \\\n            -H \"Content-Type: application/json\" \\\n            -d '{\n              \"repo_url\": \"https://github.com/" + D + "{{ github.repository }}\",\n              \"pr_number\": " + D + "{{ github.event.pull_request.number }},\n              \"api_key\": \"" + D + "{{ secrets.TESTAI_API_KEY }}\",\n              \"token\": \"" + D + "{{ secrets.GITHUB_TOKEN }}\"\n            }'";

const GITLAB = "testai:\n  stage: test\n  script:\n    - apt-get update && apt-get install -y curl\n    - curl -X POST $TESTAI_BACKEND/api/ci/run\n        -H \"Content-Type: application/json\"\n        -d '{\n          \"repo_url\": \"https://gitlab.com/$CI_PROJECT_PATH\",\n          \"pr_number\": $CI_MERGE_REQUEST_IID,\n          \"api_key\": \"$TESTAI_API_KEY\",\n          \"token\": \"$CI_JOB_TOKEN\"\n        }'\n  only:\n    - merge_requests";

const CIRCLE = "testai:\n  docker:\n    - image: curlimages/curl:latest\n  steps:\n    - run:\n        name: Run TestAI\n        command: |\n          curl -X POST $TESTAI_BACKEND/api/ci/run\n            -H \"Content-Type: application/json\"\n            -d '{\n              \"repo_url\": \"https://github.com/$CIRCLE_PROJECT_USERNAME/$CIRCLE_PROJECT_REPONAME\",\n              \"pr_number\": $CIRCLE_PR_NUMBER,\n              \"api_key\": \"$TESTAI_API_KEY\",\n              \"token\": \"$GITHUB_TOKEN\"\n            }'\n  when: on_pull_request";

const JENKINS = "stage('TestAI') {\n  steps {\n    script {\n      sh \"\"\"\n        curl -X POST $TESTAI_BACKEND/api/ci/run\n          -H \"Content-Type: application/json\"\n          -d '{\n            \"repo_url\": \"${env.CHANGE_URL}\",\n            \"pr_number\": ${env.CHANGE_ID},\n            \"api_key\": \"${env.TESTAI_API_KEY}\",\n            \"token\": \"${env.GITHUB_TOKEN}\"\n          }'\n      \"\"\"\n    }\n  }\n}";

const CI_CONFIGS = [
  { platform: "GitHub Actions", icon: Github, description: "Add to .github/workflows/testai.yml", config: GHA },
  { platform: "GitLab CI", icon: Globe, description: "Add to .gitlab-ci.yml", config: GITLAB },
  { platform: "CircleCI", icon: Terminal, description: "Add to .circleci/config.yml", config: CIRCLE },
  { platform: "Jenkins", icon: Terminal, description: "Add as a pipeline step", config: JENKINS },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 100, damping: 20 } },
};

export function CICDSetup() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [openConfig, setOpenConfig] = useState<string | null>(null);
  const [copiedConfig, setCopiedConfig] = useState<string | null>(null);
  const backendUrl = typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001")
    : "http://localhost:8001";

  useEffect(() => { fetchKeys(); }, []);

  const fetchKeys = async () => {
    setIsLoading(true);
    try {
      const json = await api.get<any>(`/api/settings/api-keys`);
      if (json) {
        setKeys((json as { keys?: ApiKey[] })?.keys || []);
      }
    } catch { /* ignore */ }
    finally { setIsLoading(false); }
  };

  const createKey = async () => {
    if (!newKeyName.trim()) return;
    try {
      const json = await api.post<{ key?: string }>(`/api/settings/api-keys`, { name: newKeyName.trim() });
      setNewKeyValue(json?.key ?? null);
      setNewKeyName("");
      setShowAddForm(false);
      fetchKeys();
    } catch { /* ignore */ }
  };

  const deleteKey = async (id: string) => {
    try {
      await api.delete(`/api/settings/api-keys/${id}`);
      setKeys((prev) => prev.filter((k) => k.id !== id));
    } catch { /* ignore */ }
  };

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedConfig(id);
      setTimeout(() => setCopiedConfig(null), 2000);
    } catch { /* ignore */ }
  };

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-6">
      {/* API Keys Section */}
      <motion.div variants={itemVariants} className="bg-surface border border-white/[0.05] rounded-3xl p-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0">
            <Key className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-neutral-100">API Keys</h3>
            <p className="text-[11px] text-neutral-500 mt-0.5">
              Generate keys for authenticating CI/CD requests to this instance.
            </p>
          </div>
        </div>

        {isLoading ? (
          <div className="mt-4 space-y-2">
            <SkeletonBlock className="h-12 w-full rounded-xl" />
            <SkeletonBlock className="h-12 w-full rounded-xl" />
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {keys.length === 0 && !newKeyValue && (
              <div className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-4 text-center">
                <p className="text-xs text-neutral-500">No API keys yet. Create one to get started.</p>
              </div>
            )}

            {keys.map((key) => (
              <div
                key={key.id}
                className="flex items-center justify-between bg-white/[0.02] border border-white/[0.05] rounded-xl px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <Key className="w-4 h-4 text-neutral-500" strokeWidth={1.5} />
                  <span className="text-xs font-medium text-neutral-300">{key.name}</span>
                  <span className="text-[10px] text-neutral-600 font-mono">
                    Created {key.createdAt ? new Date(key.createdAt).toLocaleDateString() : ""}
                  </span>
                </div>
                <button
                  onClick={() => deleteKey(key.id)}
                  className="w-7 h-7 flex items-center justify-center rounded-lg text-neutral-500 hover:text-red-400 hover:bg-red-500/10 transition-colors active:scale-[0.92]"
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              </div>
            ))}

            {/* New key reveal */}
            {newKeyValue && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4"
              >
                <p className="text-xs text-emerald-400 font-semibold mb-2">Key generated — copy it now</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs font-mono text-emerald-300 bg-zinc-950/30 rounded-lg px-3 py-2 truncate">
                    {newKeyValue}
                  </code>
                  <Button
                    size="sm"
                    onClick={() => copyToClipboard(newKeyValue, "new-key")}
                    className="h-8 px-3 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black"
                  >
                    {copiedConfig === "new-key" ? (
                      <Check className="w-3.5 h-3.5" strokeWidth={2} />
                    ) : (
                      <Copy className="w-3.5 h-3.5" strokeWidth={1.5} />
                    )}
                  </Button>
                </div>
                <button
                  onClick={() => setNewKeyValue(null)}
                  className="text-[10px] text-neutral-500 hover:text-neutral-400 mt-2 transition-colors"
                >
                  Dismiss
                </button>
              </motion.div>
            )}

            {showAddForm ? (
              <div className="flex items-center gap-2 pt-2">
                <Input
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Key name (e.g., CI/CD)"
                  className="bg-white/[0.02] border-white/[0.08] text-xs h-9 rounded-xl flex-1"
                />
                <Button
                  size="sm"
                  onClick={createKey}
                  disabled={!newKeyName.trim()}
                  className="h-9 px-4 rounded-xl text-xs bg-emerald-500 hover:bg-emerald-400 text-black"
                >
                  <Plus className="w-3.5 h-3.5 mr-1" strokeWidth={1.5} />
                  Generate
                </Button>
                <button
                  onClick={() => setShowAddForm(false)}
                  className="text-xs text-neutral-500 px-2"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowAddForm(true)}
                className="flex items-center gap-2 text-xs text-neutral-500 hover:text-neutral-300 transition-colors mt-3 pt-3 border-t border-white/[0.05] w-full"
              >
                <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
                Generate API Key
              </button>
            )}
          </div>
        )}
      </motion.div>

      {/* CI/CD Configs Section */}
      <motion.div variants={itemVariants} className="bg-surface border border-white/[0.05] rounded-3xl p-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-xl bg-zinc-500/10 flex items-center justify-center shrink-0">
            <Terminal className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-neutral-100">CI/CD Integration</h3>
            <p className="text-[11px] text-neutral-500 mt-0.5">
              Add TestAI to your CI pipeline. Set <code className="text-emerald-400/80">TESTAI_BACKEND</code> to{" "}
              <code className="text-emerald-400/80">{backendUrl}</code> and add your API key as a secret.
            </p>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-2">
          {CI_CONFIGS.map((ci, i) => (
            <motion.div key={ci.platform} layout>
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <Collapsible
                  open={openConfig === ci.platform}
                  onOpenChange={(o) => setOpenConfig(o ? ci.platform : null)}
                >
                  <CollapsibleTrigger className="w-full flex items-center justify-between bg-white/[0.02] border border-white/[0.05] rounded-xl px-4 py-3 hover:border-white/[0.1] transition-all group">
                    <div className="flex items-center gap-3">
                      <ci.icon className="w-4 h-4 text-neutral-400" strokeWidth={1.5} />
                      <span className="text-xs font-medium text-neutral-200">{ci.platform}</span>
                      <span className="text-[10px] text-neutral-500 hidden sm:inline">{ci.description}</span>
                    </div>
                    <ChevronDown
                      className={cn(
                        "w-4 h-4 text-neutral-500 transition-transform duration-200",
                        openConfig === ci.platform && "rotate-180",
                      )}
                      strokeWidth={1.5}
                    />
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="relative mt-2">
                      <pre className="bg-zinc-950/40 border border-white/[0.05] rounded-xl p-4 text-[11px] font-mono text-neutral-300 leading-relaxed overflow-x-auto whitespace-pre">
                        {ci.config}
                      </pre>
                      <button
                        onClick={() => copyToClipboard(ci.config, ci.platform)}
                        className="absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-neutral-500 hover:text-neutral-300 transition-all"
                      >
                        {copiedConfig === ci.platform ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />
                        ) : (
                          <Copy className="w-3.5 h-3.5" strokeWidth={1.5} />
                        )}
                      </button>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </motion.div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}
