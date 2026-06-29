import type { GroupedError } from "@/lib/types/pipeline";

const SEVERITY_PATTERNS: Array<[RegExp, "error" | "warning" | "info"]> = [
  [/TypeError|ReferenceError|SyntaxError|RangeError|URIError/i, "error"],
  [/AssertionError|assert\.|expect\(|should\./i, "error"],
  [/Cannot find module|Module not found|Failed to load/i, "error"],
  [/timeout|Timed?out/i, "warning"],
  [/deprecated|Warning/i, "warning"],
  [/skipped|pending|not implemented/i, "info"],
];

export function classifySeverity(msg: string): "error" | "warning" | "info" {
  for (const [re, level] of SEVERITY_PATTERNS) {
    if (re.test(msg)) return level;
  }
  return "error";
}

const STRIP_PATTERNS = [
  /`[^`]+`/g,
  /line \d+/gi,
  /at .+?:\d+:\d+/g,
  /\(.*?:\d+:\d+\)/g,
  /\d+ms/g,
  /\d+\.\d+s/g,
  /'[^']+'/g,
  /"[^"]+"/g,
];

export function extractErrorSignature(message: string): string {
  let sig = message;
  for (const re of STRIP_PATTERNS) {
    sig = sig.replace(re, "");
  }
  sig = sig.replace(/\s+/g, " ").trim().slice(0, 120);
  return sig;
}

export function groupErrors(
  items: Array<{ testName?: string; file?: string; line?: number; message: string; timestamp?: string }>,
): GroupedError[] {
  const groups = new Map<string, GroupedError>();

  for (const item of items) {
    const sig = extractErrorSignature(item.message);
    const msg = item.message;
    const type = /^(\w+Error|TypeError|SyntaxError|AssertionError)/.exec(msg)?.[1] ?? "Error";

    if (!groups.has(sig)) {
      groups.set(sig, {
        signature: sig,
        type,
        message: msg,
        count: 0,
        occurrences: [],
        firstSeen: item.timestamp,
        lastSeen: item.timestamp,
        severity: classifySeverity(msg),
      });
    }

    const group = groups.get(sig)!;
    group.count += 1;
    group.occurrences.push({
      testName: item.testName,
      file: item.file,
      line: item.line,
      message: item.timestamp ? `[${item.timestamp}] ${msg}` : msg,
    });
    if (item.timestamp && (!group.lastSeen || item.timestamp > group.lastSeen)) {
      group.lastSeen = item.timestamp;
    }
  }

  return Array.from(groups.values()).sort((a, b) => b.count - a.count);
}
