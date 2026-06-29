"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";

interface CompareBarProps {
  selectedIds: string[];
  onRemove: (id: string) => void;
  onClear: () => void;
}

export function CompareBar({ selectedIds, onRemove, onClear }: CompareBarProps) {
  const router = useRouter();
  const visible = selectedIds.length >= 2;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 25 }}
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50"
        >
          <div className="bg-zinc-900/95 backdrop-blur-lg border border-white/[0.08] rounded-2xl px-4 py-3 flex items-center gap-3 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
            <div className="text-[12px] text-zinc-400 whitespace-nowrap">
              <strong className="text-emerald-400 font-semibold">{selectedIds.length}</strong> runs selected
            </div>
            <div className="flex items-center gap-1.5">
              {selectedIds.slice(0, 3).map((id) => (
                <span key={id} className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-zinc-800 border border-white/[0.06] text-[10px] font-mono text-zinc-400">
                  {id.slice(0, 8)}
                  <button onClick={() => onRemove(id)} className="text-zinc-600 hover:text-red-400 transition-colors">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </span>
              ))}
              {selectedIds.length > 3 && (
                <span className="text-[10px] text-zinc-600 font-mono">+{selectedIds.length - 3}</span>
              )}
            </div>
            <div className="w-px h-6 bg-white/[0.06]" />
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => router.push(`/history/compare?runA=${selectedIds[0]}&runB=${selectedIds[1]}`)}
                className="px-3 py-1.5 text-[11px] font-semibold rounded-lg bg-emerald-400 text-zinc-950 hover:bg-emerald-300 transition-all"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="inline mr-1 -mt-0.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                Compare
              </button>
              <button onClick={onClear} className="px-3 py-1.5 text-[11px] rounded-lg bg-zinc-800 text-zinc-400 border border-white/[0.06] hover:text-zinc-200 transition-colors">
                Clear
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
