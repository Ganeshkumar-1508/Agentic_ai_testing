"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { Check, Loader2, Save, SplitSquareHorizontal, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface PipelineStepConfig {
  step: string;
  label: string;
  description: string;
  value: string;
}

const STEPS: PipelineStepConfig[] = [
  {
    step: "analysis",
    label: "Analysis",
    description: "Requirements analysis and edge case detection",
    value: "",
  },
  {
    step: "code_generation",
    label: "Code Generation",
    description: "Writing test code from requirements",
    value: "",
  },
  {
    step: "execution",
    label: "Execution",
    description: "Running tests and reporting results",
    value: "",
  },
];

export function PipelineModelAssignment() {
  const [config, setConfig] = useState<Record<string, string>>({});
  const [providers, setProviders] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setIsLoading(true);
    try {
      const [provRes, configRes] = await Promise.all([
        api.get<{ data?: any[] }>(`/api/settings/providers`),
        api.get<{ config?: Record<string, string> }>(`/api/settings/pipeline-config`),
      ]);
      setProviders(Array.isArray(provRes?.data) ? provRes.data : []);
      setConfig(configRes?.config || {});
    } catch {
      // Fallback to empty
    } finally {
      setIsLoading(false);
    }
  };

  const enabledProviders = providers.filter((p) => p.enabled);
  const hasProviders = enabledProviders.length > 0;

  const getOptions = () => {
    return enabledProviders.map((p) => ({
      value: `${p.provider}/${p.model}`,
      label: `${p.provider} / ${p.model}`,
    }));
  };

  const selectModel = (step: string, value: string) => {
    setConfig((prev) => ({ ...prev, [step]: value }));
    setSaveStatus("idle");
    setOpenDropdown(null);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await api.post(`/api/settings/pipeline-config`, {
        analysis: config.analysis || "",
        code_generation: config.code_generation || "",
        execution: config.execution || "",
      });
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } catch {
      setSaveStatus("error");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="bg-surface border border-white/[0.05] rounded-3xl p-6 space-y-4">
        <SkeletonBlock className="h-5 w-48" />
        <SkeletonBlock className="h-12 w-full rounded-xl" />
        <SkeletonBlock className="h-12 w-full rounded-xl" />
        <SkeletonBlock className="h-12 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 100, damping: 20 }}
      className="bg-surface border border-white/[0.05] rounded-3xl p-6"
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="w-8 h-8 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0">
          <SplitSquareHorizontal className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-neutral-100">Pipeline Model Assignment</h3>
          <p className="text-[11px] text-neutral-500 mt-0.5">
            Assign a provider to each pipeline step. Unassigned steps use the first enabled provider.
          </p>
        </div>
      </div>

      {/* No providers warning */}
      {!hasProviders && (
        <div className="mt-4 bg-amber-500/5 border border-amber-500/10 rounded-xl p-4">
          <p className="text-xs text-amber-400/80">
            No providers enabled. Enable a provider in Backend Providers first.
          </p>
        </div>
      )}

      {hasProviders && (
        <>
          {/* Step rows */}
          <div className="mt-5 space-y-2">
            {STEPS.map((step, i) => {
              const currentValue = config[step.step] || "";
              const options = getOptions();
              const selectedOption = options.find((o) => o.value === currentValue);

              return (
                <motion.div
                  key={step.step}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06, type: "spring", stiffness: 100, damping: 20 }}
                  className="relative"
                >
                  <label className="block text-[11px] font-medium text-neutral-400 mb-1.5 px-1">
                    {step.label}
                    <span className="text-neutral-600 font-normal ml-2">{step.description}</span>
                  </label>

                  {/* Custom dropdown */}
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setOpenDropdown(openDropdown === step.step ? null : step.step)}
                      className={cn(
                        "w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs transition-all",
                        "bg-white/[0.02] border border-white/[0.08]",
                        "hover:border-white/[0.12] hover:bg-white/[0.03]",
                        "active:scale-[0.99]",
                        selectedOption ? "text-neutral-200" : "text-neutral-500",
                      )}
                    >
                      <span className="font-mono">
                        {selectedOption ? selectedOption.label : "Auto (first enabled)"}
                      </span>
                      <ChevronDown
                        className={cn(
                          "w-3.5 h-3.5 text-neutral-500 transition-transform duration-200",
                          openDropdown === step.step && "rotate-180",
                        )}
                        strokeWidth={1.5}
                      />
                    </button>

                    {/* Dropdown menu */}
                    {openDropdown === step.step && (
                      <motion.div
                        initial={{ opacity: 0, y: -4, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={{ type: "spring", stiffness: 200, damping: 25 }}
                        className="absolute z-20 mt-1 w-full bg-neutral-900 border border-white/[0.1] rounded-xl overflow-hidden shadow-xl"
                      >
                        <button
                          onClick={() => selectModel(step.step, "")}
                          className={cn(
                            "w-full flex items-center justify-between px-3 py-2.5 text-xs text-left transition-colors",
                            "hover:bg-white/[0.05] text-neutral-500 font-mono",
                            !currentValue && "text-emerald-400 bg-emerald-500/5",
                          )}
                        >
                          Auto (first enabled)
                          {!currentValue && <Check className="w-3 h-3" strokeWidth={2.5} />}
                        </button>
                        {options.map((opt) => (
                          <button
                            key={opt.value}
                            onClick={() => selectModel(step.step, opt.value)}
                            className={cn(
                              "w-full flex items-center justify-between px-3 py-2.5 text-xs text-left transition-colors",
                              "hover:bg-white/[0.05] font-mono",
                              currentValue === opt.value
                                ? "text-emerald-400 bg-emerald-500/5"
                                : "text-neutral-300",
                            )}
                          >
                            {opt.label}
                            {currentValue === opt.value && (
                              <Check className="w-3 h-3" strokeWidth={2.5} />
                            )}
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* Click outside to close dropdown */}
          {openDropdown && (
            <div
              className="fixed inset-0 z-10"
              onClick={() => setOpenDropdown(null)}
            />
          )}

          {/* Save bar */}
          <div className="mt-5 flex items-center justify-between pt-4 border-t border-white/[0.05]">
            {saveStatus === "saved" ? (
              <div className="flex items-center gap-1.5 text-xs text-emerald-400">
                <Check className="w-3.5 h-3.5" strokeWidth={2} />
                Pipeline config saved
              </div>
            ) : saveStatus === "error" ? (
              <div className="text-xs text-red-400">Failed to save</div>
            ) : (
              <div className="text-[11px] text-neutral-500">
                {Object.values(config).filter(Boolean).length} of {STEPS.length} steps assigned
              </div>
            )}

            <Button
              onClick={handleSave}
              disabled={isSaving}
              className="h-8 px-4 rounded-xl text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1.5 transition-all active:scale-[0.97]"
            >
              {isSaving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} />
              ) : (
                <Save className="w-3.5 h-3.5" strokeWidth={1.5} />
              )}
              {isSaving ? "Saving..." : "Save"}
            </Button>
          </div>
        </>
      )}
    </motion.div>
  );
}
