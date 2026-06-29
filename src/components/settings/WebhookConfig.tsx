"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import {
  Webhook,
  Plus,
  Trash2,
  Check,
  X,
  Loader2,
  Globe,
  Radio,
} from "lucide-react";

interface WebhookEntry {
  id: string;
  name: string;
  url: string;
  type: "webhook" | "callback";
  events: string[];
  enabled: boolean;
}

export function WebhookConfig() {
  const [webhooks, setWebhooks] = useState<WebhookEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [newType, setNewType] = useState<"webhook" | "callback">("webhook");

  useEffect(() => {
    fetchWebhooks();
  }, []);

  const fetchWebhooks = async () => {
    setIsLoading(true);
    try {
      const json = await api.get<{ webhooks?: WebhookEntry[] }>(`/api/settings/webhooks`);
      setWebhooks(json?.webhooks ?? []);
    } catch {
      // Fallback
    } finally {
      setIsLoading(false);
    }
  };

  const addWebhook = async () => {
    if (!newName.trim() || !newUrl.trim()) return;
    try {
      const json = await api.post<{ webhook?: WebhookEntry }>(`/api/settings/webhooks`, {
        name: newName.trim(),
        url: newUrl.trim(),
        type: newType,
        events: ["run:completed"],
        enabled: true,
      });
      if (json?.webhook) {
        setWebhooks((prev) => [...prev, json.webhook!]);
        setNewName("");
        setNewUrl("");
        setShowAddForm(false);
      }
    } catch {
      // Handle error
    }
  };

  const toggleWebhook = async (id: string, enabled: boolean) => {
    setWebhooks((prev) => prev.map((w) => (w.id === id ? { ...w, enabled } : w)));
    try {
      await api.patch(`/api/settings/webhooks/${id}`, { enabled });
    } catch {
      setWebhooks((prev) => prev.map((w) => (w.id === id ? { ...w, enabled: !enabled } : w)));
    }
  };

  const deleteWebhook = async (id: string) => {
    try {
      await api.delete(`/api/settings/webhooks/${id}`);
      setWebhooks((prev) => prev.filter((w) => w.id !== id));
    } catch {
      // Handle error
    }
  };

  if (isLoading) {
    return (
      <div className="bg-surface border border-white/[0.05] rounded-3xl p-6 space-y-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <SkeletonBlock key={i} className="h-16 w-full rounded-[1rem]" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-surface border border-white/[0.05] rounded-3xl divide-y divide-white/[0.05]">
        {webhooks.map((webhook) => (
          <div key={webhook.id} className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={cn(
                "w-10 h-10 rounded-xl flex items-center justify-center",
                webhook.type === "callback"
                  ? "bg-emerald-500/10"
                  : "bg-zinc-500/10",
              )}>
                {webhook.type === "callback" ? (
                  <Radio className="w-5 h-5 text-emerald-400" strokeWidth={1.5} />
                ) : (
                  <Webhook className="w-5 h-5 text-zinc-400" strokeWidth={1.5} />
                )}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-neutral-100">{webhook.name}</span>
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[9px] px-1 py-0 rounded",
                      webhook.type === "callback"
                        ? "text-emerald-400 border-emerald-500/30"
                        : "text-zinc-400 border-zinc-500/30",
                    )}
                  >
                    {webhook.type}
                  </Badge>
                </div>
                <p className="text-[10px] text-neutral-500 font-mono mt-0.5">{webhook.url}</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => deleteWebhook(webhook.id)}
                className="w-7 h-7 text-neutral-500 hover:text-red-400"
              >
                <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
              </Button>
              <Switch
                checked={webhook.enabled}
                onCheckedChange={(v) => toggleWebhook(webhook.id, v)}
              />
            </div>
          </div>
        ))}

        {webhooks.length === 0 && (
          <div className="p-6 text-center">
            <Webhook className="w-8 h-8 text-neutral-600 mx-auto mb-2" strokeWidth={1.2} />
            <p className="text-sm text-neutral-500">No webhooks configured</p>
            <p className="text-xs text-neutral-600 mt-1">
              Add a webhook URL to receive test results when a run completes
            </p>
          </div>
        )}
      </div>

      {showAddForm ? (
        <div className="bg-surface border border-white/[0.05] rounded-3xl p-5">
          <h4 className="text-sm font-semibold text-neutral-100 mb-4">Add Webhook / Callback</h4>
          <div className="space-y-3">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Name (e.g., Slack, Jenkins)"
              className="bg-white/[0.02] border-white/[0.08] text-sm"
            />
            <Input
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="https://your-server.com/webhook"
              className="bg-white/[0.02] border-white/[0.08] text-sm font-mono"
            />
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="webhookType"
                  checked={newType === "webhook"}
                  onChange={() => setNewType("webhook")}
                  className="text-emerald-500"
                />
                <span className="text-xs text-neutral-300">Webhook (async)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="webhookType"
                  checked={newType === "callback"}
                  onChange={() => setNewType("callback")}
                  className="text-emerald-500"
                />
                <span className="text-xs text-neutral-300">Callback (sync + store response)</span>
              </label>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={addWebhook}
                disabled={!newName.trim() || !newUrl.trim()}
                className="bg-emerald-500 hover:bg-emerald-400 text-xs rounded-xl"
              >
                <Check className="w-3.5 h-3.5 mr-1" strokeWidth={2} />
                Add
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowAddForm(false)}
                className="text-xs rounded-xl text-neutral-400"
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <Button
          variant="outline"
          onClick={() => setShowAddForm(true)}
          className="w-full py-6 border-dashed border-white/[0.08] rounded-3xl text-sm text-neutral-400 gap-2"
        >
          <Plus className="w-4 h-4" strokeWidth={1.5} />
          Add Webhook / Callback
        </Button>
      )}
    </div>
  );
}
