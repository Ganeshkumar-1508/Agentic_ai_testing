"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { api } from "@/lib/api/api-client";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import {
  Loader2, Save, Cpu, HardDrive, Globe, Terminal, Server,
  Monitor, Wifi, Key, User, Network, Clock, Sliders,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SizePreset {
  cpus: string;
  memory: string;
  description: string;
}

interface SandboxConfig {
  size: string;
  image: string;
  network: string;
  size_presets: Record<string, SizePreset>;
  effective_cpus: string;
  effective_memory: string;
  default_backend_type: string;
  default_timeout: string;
  container_persistent: string;
  ssh_host: string;
  ssh_user: string;
  ssh_port: string;
  ssh_key_path: string;
}

const SIZE_OPTIONS = ["auto", "small", "medium", "large", "xlarge"] as const;
const BACKEND_OPTIONS = [
  { value: "local", label: "Local", icon: Monitor, desc: "Direct host execution" },
  { value: "docker", icon: Server, label: "Docker", desc: "Isolated containers" },
  { value: "ssh", icon: Terminal, label: "SSH", desc: "Remote server" },
] as const;
const NETWORK_MODES = ["bridge", "none", "host"] as const;

export function RunnerConfigSettings() {
  const [config, setConfig] = useState<SandboxConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<{ config: SandboxConfig }>("/api/settings/sandbox")
      .then((d) => setConfig(d.config))
      .catch((e) => setError(e?.message || "Failed to load config"))
      .finally(() => setLoading(false));
  }, []);

  const updateConfig = async (updates: Partial<SandboxConfig>) => {
    setSaving(true);
    try {
      await api.post("/api/settings/sandbox", updates);
      const fresh = await api.get<{ config: SandboxConfig }>("/api/settings/sandbox");
      setConfig(fresh.config);
      toast.success("Sandbox config saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="space-y-4">
      <SkeletonBlock className="h-4 w-48" />
      <SkeletonBlock className="h-20 w-full" />
      <SkeletonBlock className="h-20 w-full" />
    </div>
  );

  if (error) return <ErrorState message={error} onRetry={() => { setLoading(true); setError(null); }} />;

  if (!config) return null;

  const backendType = config.default_backend_type || "local";
  const isDocker = backendType === "docker";
  const isSSH = backendType === "ssh";

  return (
    <div className="space-y-6">
      <p className="text-[11px] text-zinc-500">
        Configure execution environment. Changes apply to new sessions.
      </p>

      {/* Backend Type */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Terminal className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
          <span className="text-[11px] font-medium text-zinc-300">Execution Backend</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {BACKEND_OPTIONS.map(({ value, label, icon: Icon, desc }) => (
            <button
              key={value}
              onClick={() => updateConfig({ default_backend_type: value })}
              disabled={saving}
              className={cn(
                "flex flex-col items-start gap-1 p-3 rounded-xl border transition-all text-left",
                backendType === value
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                  : "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:border-zinc-700"
              )}
            >
              <div className="flex items-center gap-2">
                <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
                <span className="text-[12px] font-medium">{label}</span>
              </div>
              <span className="text-[10px] text-zinc-600 leading-tight">{desc}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Backend-specific config */}
      <AnimatePresence mode="wait">
        <motion.div
          key={backendType}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 4 }}
          transition={{ duration: 0.15 }}
        >
          {isDocker && (
            <div className="space-y-5 border-t border-zinc-800/50 pt-5">
              {/* Size Presets */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Cpu className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                  <span className="text-[11px] font-medium text-zinc-300">Sandbox Size</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {SIZE_OPTIONS.map((size) => {
                    const preset = size === "auto" ? null : config.size_presets?.[size];
                    const isActive = (config.size || "auto") === size;
                    return (
                      <button
                        key={size}
                        onClick={() => updateConfig({ size })}
                        disabled={saving}
                        className={cn(
                          "flex flex-col items-start p-3 rounded-xl border transition-all text-left",
                          isActive
                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                            : "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:border-zinc-700"
                        )}
                      >
                        <span className="text-[12px] font-medium capitalize">{size}</span>
                        {preset ? (
                          <span className="text-[10px] text-zinc-600 mt-0.5">
                            {preset.cpus} CPU / {preset.memory}
                          </span>
                        ) : (
                          <span className="text-[10px] text-zinc-600 mt-0.5">Default from env</span>
                        )}
                        {preset && (
                          <span className="text-[9px] text-zinc-700 mt-1">{preset.description}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
                {(config.size || "auto") !== "auto" && (
                  <p className="text-[10px] text-zinc-600 mt-2">
                    Effective: {config.effective_cpus} CPU / {config.effective_memory}
                  </p>
                )}
              </div>

              {/* Image */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <HardDrive className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                  <span className="text-[11px] font-medium text-zinc-300">Docker Image</span>
                </div>
                <input
                  value={config.image || ""}
                  onChange={(e) => setConfig({ ...config, image: e.target.value })}
                  onBlur={() => updateConfig({ image: config.image })}
                  className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg px-3 py-1.5 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30 font-mono"
                  placeholder="nikolaik/python-nodejs:python3.11-nodejs20"
                />
                <p className="text-[9px] text-zinc-600 mt-1">Base image for sandbox containers</p>
              </div>

              {/* Network */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Globe className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                  <span className="text-[11px] font-medium text-zinc-300">Network Mode</span>
                </div>
                <div className="flex gap-2">
                  {NETWORK_MODES.map((mode) => (
                    <button
                      key={mode}
                      onClick={() => updateConfig({ network: mode })}
                      disabled={saving}
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors",
                        config.network === mode
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                          : "bg-zinc-900/50 text-zinc-500 border border-zinc-800 hover:text-zinc-300"
                      )}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
                <p className="text-[9px] text-zinc-600 mt-1">bridge = normal, none = no internet, host = shared with host</p>
              </div>
            </div>
          )}

          {isSSH && (
            <div className="space-y-4 border-t border-zinc-800/50 pt-5">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Network className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                  <span className="text-[11px] font-medium text-zinc-300">Host</span>
                </div>
                <Input
                  value={config.ssh_host || ""}
                  onChange={(e) => setConfig({ ...config, ssh_host: e.target.value })}
                  onBlur={() => updateConfig({ ssh_host: config.ssh_host })}
                  placeholder="my-server.example.com"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <User className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                    <span className="text-[11px] font-medium text-zinc-300">User</span>
                  </div>
                  <Input
                    value={config.ssh_user || ""}
                    onChange={(e) => setConfig({ ...config, ssh_user: e.target.value })}
                    onBlur={() => updateConfig({ ssh_user: config.ssh_user })}
                    placeholder="root"
                  />
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Wifi className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                    <span className="text-[11px] font-medium text-zinc-300">Port</span>
                  </div>
                  <Input
                    value={config.ssh_port || "22"}
                    onChange={(e) => setConfig({ ...config, ssh_port: e.target.value })}
                    onBlur={() => updateConfig({ ssh_port: config.ssh_port })}
                    placeholder="22"
                  />
                </div>
              </div>
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Key className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                  <span className="text-[11px] font-medium text-zinc-300">Key Path</span>
                </div>
                <Input
                  value={config.ssh_key_path || ""}
                  onChange={(e) => setConfig({ ...config, ssh_key_path: e.target.value })}
                  onBlur={() => updateConfig({ ssh_key_path: config.ssh_key_path })}
                  placeholder="~/.ssh/id_rsa"
                />
                <p className="text-[9px] text-zinc-600 mt-1">Path to SSH private key on the TestAI host</p>
              </div>
            </div>
          )}

          {!isDocker && !isSSH && (
            <div className="border-t border-zinc-800/50 pt-5">
              <div className="p-3 rounded-lg bg-zinc-900/30 border border-zinc-800/50">
                <p className="text-[11px] text-zinc-500 leading-relaxed">
                  Commands run directly on the TestAI host machine. No container isolation, no SSH overhead.
                  Suitable for development and trusted execution environments.
                </p>
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Global resource settings */}
      <div className="border-t border-zinc-800/50 pt-5 space-y-4">
        <span className="text-[11px] font-medium text-zinc-300 flex items-center gap-2">
          <Sliders className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
          Resource Limits
        </span>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
              <span className="text-[11px] font-medium text-zinc-300">Default Timeout (s)</span>
            </div>
            <Input
              value={config.default_timeout || "120"}
              onChange={(e) => setConfig({ ...config, default_timeout: e.target.value })}
              onBlur={() => updateConfig({ default_timeout: config.default_timeout })}
              placeholder="120"
            />
          </div>
          {isDocker && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Save className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                <span className="text-[11px] font-medium text-zinc-300">Persistent Volumes</span>
              </div>
              <div className="flex items-center gap-2 h-9">
                <Switch
                  checked={config.container_persistent !== "false"}
                  onCheckedChange={(v) => updateConfig({ container_persistent: v ? "true" : "false" })}
                />
                <span className="text-[10px] text-zinc-600">
                  {config.container_persistent !== "false" ? "Enabled — data survives restarts" : "Disabled — ephemeral"}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
