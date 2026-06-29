"use client";

import { useState, useEffect } from "react";
import { usePathname, useSelectedLayoutSegment } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import AppSidebar from "@/components/layout/AppSidebar";
import AppHeader from "@/components/layout/AppHeader";
import { CommandPalette } from "@/components/shared/CommandPalette";
import { BackToTop } from "@/components/shared/BackToTop";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { useKeyboardShortcuts } from "@/lib/hooks/use-keyboard-shortcuts";
import { usePipelineNotifications } from "@/lib/hooks/use-pipeline-notifications";
import { toast } from "sonner";

function LoadingBar() {
  const pathname = usePathname();
  const [loading, setLoading] = useState(false);
  const [prevPath, setPrevPath] = useState(pathname);

  useEffect(() => {
    if (pathname !== prevPath) {
      setLoading(true);
      setPrevPath(pathname);
      const timer = setTimeout(() => setLoading(false), 400);
      return () => clearTimeout(timer);
    }
  }, [pathname, prevPath]);

  return (
    <div className="fixed top-0 left-0 right-0 z-[100] h-[2px] pointer-events-none">
      <motion.div
        className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500"
        initial={{ scaleX: 0 }}
        animate={{ scaleX: loading ? 1 : 0 }}
        transition={{ duration: loading ? 0.3 : 0.5, ease: loading ? [0.16, 1, 0.3, 1] : [0.16, 1, 0.3, 1] }}
        style={{ transformOrigin: "0% 50%" }}
      />
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const segment = useSelectedLayoutSegment();
  useKeyboardShortcuts();
  usePipelineNotifications();

  useEffect(() => {
    const onDone = () => toast.success("Pipeline completed");
    const onError = (e: Event) => toast.error((e as CustomEvent)?.detail?.message || "Pipeline failed");
    window.addEventListener("pipeline:done", onDone);
    window.addEventListener("pipeline:error", onError);
    return () => {
      window.removeEventListener("pipeline:done", onDone);
      window.removeEventListener("pipeline:error", onError);
    };
  }, []);

  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  useEffect(() => {
    const handler = () => setShortcutsOpen(true);
    window.addEventListener("open:shortcuts", handler);
    return () => window.removeEventListener("open:shortcuts", handler);
  }, []);

  const shortcuts = [
    { keys: "g + d", desc: "Dashboard" },
    { keys: "g + p", desc: "Pipeline" },
    { keys: "g + h", desc: "Run History" },
    { keys: "g + c", desc: "Run Comparison" },
    { keys: "g + f", desc: "Flaky Tests" },
    { keys: "g + t", desc: "Traceability" },
    { keys: "g + r", desc: "Requirements" },
    { keys: "g + s", desc: "Settings" },
    { keys: "Cmd + K", desc: "Command palette" },
    { keys: "?", desc: "Show this help" },
  ];

  return (
    <>
      <AnimatePresence>
        {shortcutsOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[200] bg-zinc-950/60 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShortcutsOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              onClick={(e) => e.stopPropagation()}
              className="bg-zinc-900 border border-zinc-800/60 rounded-[1.5rem] p-6 max-w-sm w-full mx-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
            >
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-sm font-semibold text-neutral-100">Keyboard Shortcuts</h2>
                <button onClick={() => setShortcutsOpen(false)} className="p-1 rounded-lg hover:bg-zinc-800/50 text-zinc-600 hover:text-zinc-400 transition-colors">
                  <X size={14} strokeWidth={1.5} />
                </button>
              </div>
              <div className="space-y-2">
                {shortcuts.map((s) => (
                  <div key={s.keys} className="flex items-center justify-between text-sm">
                    <span className="text-neutral-400">{s.desc}</span>
                    <kbd className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800/60 border border-zinc-700/30 text-zinc-500">{s.keys}</kbd>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-zinc-700 mt-4 text-center">Press ? to toggle this help</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <LoadingBar />
      <BackToTop />
      <ErrorBoundary label="Dashboard">
        <div className="flex min-h-[100dvh] overflow-hidden">
          <AppSidebar />
          <main id="main-content" className="flex-1 overflow-auto">
            <AppHeader />
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={segment ?? pathname}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              >
                <div className="max-w-7xl mx-auto p-8">{children}</div>
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
      </ErrorBoundary>
    </>
  );
}
