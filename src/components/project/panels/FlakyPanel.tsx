"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ShieldOff } from "lucide-react";
import { api } from "@/lib/api/api-client";

export function FlakyPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["flaky-tests"],
    queryFn: async () => {
      return (await api.get<any>(`/api/tests/flaky?limit=50`))?? {};
    },
  });

  const toggleQuarantine = useMutation({
    mutationFn: async ({ testName, branch, quarantine }: { testName: string; branch: string; quarantine: boolean }) => {
      await api.post(`/api/tests/flaky/${testName}/quarantine`, { quarantine, branch });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["flaky-tests"] }),
  });

  const flaky = (data as any)?.flaky ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-neutral-100">Flaky Test Management</h2>
        <p className="text-sm text-neutral-500 mt-1">Auto-heal and quarantine for flaky tests</p>
      </div>
      {flaky.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-48 text-neutral-600 text-sm gap-3">
          <ShieldOff className="w-10 h-10 opacity-30" strokeWidth={1} />
          <p>No flaky tests detected</p>
        </div>
      )}
      {isLoading && (
        <div className="flex items-center justify-center h-48 text-neutral-500 text-sm">Loading flaky tests...</div>
      )}
      <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06]">
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Test Name</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Flaky Score</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Runs</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Pass/Fail</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Status</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-neutral-500">Action</th>
              </tr>
            </thead>
            <tbody>
              {flaky.map((t: any) => (
                <tr key={t.testName + t.branch} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="px-4 py-3 text-neutral-300 font-mono text-xs max-w-[200px] truncate">{t.testName}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-amber-500" style={{ width: `${Math.min((t.flakyScore ?? 0) * 100, 100)}%` }} />
                      </div>
                      <span className="text-xs text-neutral-400 font-mono">{((t.flakyScore ?? 0) * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-400 font-mono">{t.totalRuns}</td>
                  <td className="px-4 py-3 text-xs">
                    <span className="text-emerald-400 font-mono">{t.passCount}</span>
                    <span className="text-neutral-600 mx-1">/</span>
                    <span className="text-red-400 font-mono">{t.failCount}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                      t.isQuarantined ? "bg-amber-500/10 text-amber-400" : "bg-emerald-500/10 text-emerald-400"
                    }`}>
                      {t.isQuarantined ? "Quarantined" : "Active"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => toggleQuarantine.mutate({
                        testName: t.testName, branch: t.branch || "", quarantine: !t.isQuarantined,
                      })}
                      className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
                    >
                      {t.isQuarantined ? "Release" : "Quarantine"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
