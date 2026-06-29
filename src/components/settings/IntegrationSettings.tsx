"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Slack, GitBranch, Bug, BookOpen, Trash2, ToggleLeft, ToggleRight,
  ExternalLink, Plus, Check, KeyRound,
} from "lucide-react";
import { api } from "@/lib/api/api-client";

interface Integration {
  id: string;
  platform: string;
  enabled: boolean;
  config: Record<string, string>;
  projectMappings: Array<{ repo: string; project?: string }>;
  createdAt?: string;
}

const PLATFORMS = [
  {
    id: "slack",
    label: "Slack",
    icon: Slack,
    desc: "Tag @testai in any channel to create runs. Get PR notifications back.",
    fields: [
      { key: "bot_token", label: "Bot Token", placeholder: "xoxb-...", secret: true },
      { key: "signing_secret", label: "Signing Secret", placeholder: "abc123...", secret: true },
      { key: "app_id", label: "App ID", placeholder: "A0..." },
    ],
    setupUrl: "https://api.slack.com/apps",
  },
  {
    id: "linear",
    label: "Linear",
    icon: GitBranch,
    desc: "Assign issues to TestAI. Auto-implements and opens PRs.",
    fields: [
      { key: "api_key", label: "API Key", placeholder: "lin_api_...", secret: true },
      { key: "team_id", label: "Team ID", placeholder: "..." },
    ],
    setupUrl: "https://linear.app/settings/api",
  },
  {
    id: "jira",
    label: "Jira",
    icon: BookOpen,
    desc: "Add the testai label to trigger implementation. PR link posted to issue.",
    fields: [
      { key: "base_url", label: "Instance URL", placeholder: "https://your-domain.atlassian.net" },
      { key: "email", label: "Email", placeholder: "you+tembo@company.com" },
      { key: "api_token", label: "API Token", placeholder: "...", secret: true },
    ],
    setupUrl: "https://id.atlassian.com/manage/api-tokens",
  },
  {
    id: "sentry",
    label: "Sentry",
    icon: Bug,
    desc: "Detect errors, analyze stack traces, open auto-fix PRs.",
    fields: [
      { key: "auth_token", label: "Auth Token", placeholder: "sntrys_...", secret: true },
      { key: "org_slug", label: "Organization Slug", placeholder: "..." },
      { key: "webhook_secret", label: "Webhook Secret", placeholder: "...", secret: true },
    ],
    setupUrl: "https://sentry.io/settings/account/api/auth-tokens/",
  },
  {
    id: "github",
    label: "GitHub",
    icon: KeyRound,
    desc: "Personal Access Token for git push and PR creation. Injected as GH_TOKEN into sandboxes.",
    fields: [
      { key: "token", label: "Personal Access Token", placeholder: "ghp_...", secret: true },
    ],
    setupUrl: "https://github.com/settings/tokens?description=testai&scopes=repo,workflow",
  },
];

export function IntegrationSettings() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [mappings, setMappings] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["integrations"],
    queryFn: async () => {
      const json = await api.get<{ integrations?: Integration[] }>(`/api/integrations/configs`);
      return json?.integrations ?? [];
    },
  });

  const upsertMut = useMutation({
    mutationFn: async (body: { platform: string; enabled: boolean; config: Record<string, string>; project_mappings: string[] }) => {
      await api.post(`/api/integrations/configs`, body);
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["integrations"] }); toast.success("Saved"); },
    onError: () => toast.error("Failed to save"),
  });

  const deleteMut = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/api/integrations/configs/${id}`); },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["integrations"] }); toast.success("Removed"); },
  });

  const integrations = data ?? [];
  const getStatus = (platform: string) => integrations.find((i) => i.platform === platform);

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 rounded-[2rem] shimmer-bg" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {PLATFORMS.map((platform, pi) => {
        const Icon = platform.icon;
        const existing = getStatus(platform.id);
        const isEditing = editing === platform.id;

        return (
          <motion.div
            key={platform.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: pi * 0.05, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              "rounded-[2rem] border transition-all duration-200 overflow-hidden",
              existing?.enabled
                ? "border-emerald-500/15 bg-emerald-500/[0.02]"
                : "border-white/[0.05] shimmer-bg",
            )}
          >
            {/* Header */}
            <div className="flex items-center gap-4 px-5 py-4">
              <div className={cn(
                "w-10 h-10 rounded-xl flex items-center justify-center shrink-0",
                existing?.enabled ? "bg-emerald-500/10" : "bg-white/[0.03]",
              )}>
                <Icon className={cn("w-5 h-5", existing?.enabled ? "text-emerald-400" : "text-zinc-600")} strokeWidth={1.5} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-zinc-100">{platform.label}</span>
                  {existing?.enabled && (
                    <span className="text-[9px] font-medium text-emerald-400 px-1.5 py-0.5 rounded bg-emerald-500/10">connected</span>
                  )}
                </div>
                <p className="text-xs text-zinc-600 mt-0.5">{platform.desc}</p>
              </div>
              <div className="flex items-center gap-2">
                {existing ? (
                  <>
                    <button onClick={() => upsertMut.mutate({ platform: platform.id, enabled: !existing.enabled, config: existing.config as Record<string, string>, project_mappings: existing.projectMappings.map(m => m.repo) })}
                      className="p-1.5 rounded-lg hover:bg-white/[0.05] transition-colors">
                      {existing.enabled
                        ? <ToggleRight className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                        : <ToggleLeft className="w-4 h-4 text-zinc-600" strokeWidth={1.5} />}
                    </button>
                    <button onClick={() => { if (confirm("Remove this integration?")) deleteMut.mutate(existing.id); }}
                      className="p-1.5 rounded-lg hover:bg-red-500/10 text-zinc-600 hover:text-red-400 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </button>
                  </>
                ) : (
                  <button onClick={() => { setEditing(platform.id); setFormValues({}); setMappings(""); }}
                    className="flex items-center gap-1.5 px-3 h-8 rounded-xl bg-emerald-500/10 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/20 transition-colors active:scale-[0.97]">
                    <Plus className="w-3 h-3" strokeWidth={2} /> Connect
                  </button>
                )}
              </div>
            </div>

            {/* Expanded config form */}
            <AnimatePresence>
              {isEditing && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden border-t border-white/[0.05]">
                  <div className="p-5 space-y-4">
                    {platform.fields.map((field) => (
                      <div key={field.key} className="space-y-1">
                        <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">{field.label}</label>
                        <input
                          type={field.secret ? "password" : "text"}
                          value={formValues[field.key] ?? ""}
                          onChange={(e) => setFormValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                          placeholder={field.placeholder}
                          className="w-full h-9 px-3 rounded-xl bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30 font-mono transition-colors"
                        />
                      </div>
                    ))}

                    <div className="space-y-1">
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Repo Mappings</label>
                      <input value={mappings} onChange={(e) => setMappings(e.target.value)}
                        placeholder="org/repo1, org/repo2"
                        className="w-full h-9 px-3 rounded-xl bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30 font-mono" />
                      <p className="text-[9px] text-zinc-700">Comma-separated repo identifiers that this integration can access</p>
                    </div>

                    {platform.setupUrl && (
                      <a href={platform.setupUrl} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors">
                        <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
                        Create app on {platform.label}
                      </a>
                    )}

                    <div className="flex items-center gap-2 pt-1">
                      <button onClick={() => upsertMut.mutate({
                        platform: platform.id, enabled: true, config: formValues,
                        project_mappings: mappings.split(",").map((s) => s.trim()).filter(Boolean),
                      })}
                        className="flex items-center gap-1.5 px-4 h-9 rounded-xl bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors active:scale-[0.97]">
                        <Check className="w-3.5 h-3.5" strokeWidth={2} /> Save
                      </button>
                      <button onClick={() => setEditing(null)}
                        className="px-3 h-9 rounded-xl text-xs text-zinc-600 hover:text-zinc-400 transition-colors">Cancel</button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        );
      })}
    </div>
  );
}
