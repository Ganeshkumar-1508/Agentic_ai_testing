"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const NAV_SHORTCUTS: Record<string, string> = {
  "g d": "/dashboard",
  "g p": "/pipeline",
  "g f": "/flaky-tests",
  "g h": "/history",
  "g c": "/history/compare",
  "g t": "/traceability",
  "g r": "/requirements",
  "g s": "/settings",
  "g a": "/agents",
};

export function useKeyboardShortcuts() {
  const router = useRouter();
  let buffer = "";

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input
      if ((e.target as HTMLElement)?.tagName === "INPUT" || (e.target as HTMLElement)?.tagName === "TEXTAREA") return;

      // ? for help
      if (e.key === "?" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("open:shortcuts"));
        return;
      }

      // Cmd/Ctrl + B — toggle sidebar
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("toggle:sidebar"));
        return;
      }

      // g + letter navigation
      if (e.key === "g") {
        buffer = "g";
        setTimeout(() => { buffer = ""; }, 500);
        return;
      }

      if (buffer === "g") {
        buffer = "";
        const href = NAV_SHORTCUTS[`g ${e.key}`];
        if (href) {
          e.preventDefault();
          router.push(href);
        }
      }
    };

    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [router]);
}
