// Ported from DeerFlow (MIT License, Bytedance Ltd.)
// Original: reference/deer-flow/frontend/src/core/streamdown/preprocess.ts

import { normalizeMermaidMarkdown } from "./mermaid";

const MERMAID_BLOCK_HINT_RE = /mermaid/i;

const MAX_BLOCKQUOTE_DEPTH = 100;
const DEEP_BLOCKQUOTE_HINT_RE = new RegExp(
  `^(?:[ \\t]*>){${MAX_BLOCKQUOTE_DEPTH + 1}}`,
  "m",
);
const BLOCKQUOTE_PREFIX_RE = /^ {0,3}(?:[ \t]*>)+/;
const CODE_FENCE_RE = /^ {0,3}(?:```|~~~)/;
const INDENTED_CODE_RE = /^(?: {4}|\t)/;

const MAX_LIST_INDENT = 200;
const DEEP_INDENT_HINT_RE = new RegExp(`^[ \\t]{${MAX_LIST_INDENT + 1},}`, "m");

export function capBlockquoteNesting(markdown: string): string {
  if (!DEEP_BLOCKQUOTE_HINT_RE.test(markdown)) {
    return markdown;
  }

  let insideFence = false;
  return markdown
    .split("\n")
    .map((line) => {
      if (CODE_FENCE_RE.test(line)) {
        insideFence = !insideFence;
        return line;
      }
      if (insideFence || INDENTED_CODE_RE.test(line)) {
        return line;
      }
      const match = BLOCKQUOTE_PREFIX_RE.exec(line);
      if (!match) {
        return line;
      }
      const prefix = match[0];
      let depth = 0;
      for (let i = 0; i < prefix.length; i++) {
        if (prefix[i] === ">") {
          depth += 1;
          if (depth > MAX_BLOCKQUOTE_DEPTH) {
            return line.slice(0, i) + line.slice(prefix.length);
          }
        }
      }
      return line;
    })
    .join("\n");
}

export function capListNesting(markdown: string): string {
  if (!DEEP_INDENT_HINT_RE.test(markdown)) {
    return markdown;
  }

  let insideFence = false;
  return markdown
    .split("\n")
    .map((line) => {
      if (CODE_FENCE_RE.test(line)) {
        insideFence = !insideFence;
        return line;
      }
      if (insideFence) {
        return line;
      }
      const whitespace = /^[ \t]*/.exec(line)![0];
      if (whitespace.length <= MAX_LIST_INDENT) {
        return line;
      }
      return " ".repeat(MAX_LIST_INDENT) + line.slice(whitespace.length);
    })
    .join("\n");
}

export function capMarkdownNesting(markdown: string): string {
  return capListNesting(capBlockquoteNesting(markdown));
}

type MathDelimiter = {
  close: ")" | "]";
  replacement: "$" | "$$";
};

type DelimiterState = {
  openBlock: MathDelimiter | null;
  inlineCodeDelimiterLength: number | null;
};

function consumeBacktickRun(line: string, index: number): number {
  let runLength = 0;
  while (line[index + runLength] === "`") {
    runLength += 1;
  }
  return runLength;
}

function convertLatexDelimitersInLine(
  line: string,
  state: DelimiterState,
): { line: string; state: DelimiterState } {
  let result = "";
  let i = 0;
  let inlineCodeDelimiterLength = state.inlineCodeDelimiterLength;
  let currentBlock = state.openBlock;

  while (i < line.length) {
    if (line[i] === "`") {
      const runLength = consumeBacktickRun(line, i);
      result += line.slice(i, i + runLength);
      if (!currentBlock) {
        if (inlineCodeDelimiterLength === null) {
          inlineCodeDelimiterLength = runLength;
        } else if (runLength === inlineCodeDelimiterLength) {
          inlineCodeDelimiterLength = null;
        }
      }
      i += runLength;
      continue;
    }

    const two = line.slice(i, i + 2);
    const inInlineCode = inlineCodeDelimiterLength !== null;

    if (two === "\\\\" && !inInlineCode) {
      result += two;
      i += 2;
      continue;
    }

    if (!inInlineCode && currentBlock?.close === two) {
      result += currentBlock.replacement;
      currentBlock = null;
      i += 2;
      continue;
    }

    if (!inInlineCode && !currentBlock && (two === "\\(" || two === "\\[")) {
      const isDisplay = two === "\\[";
      currentBlock = {
        close: isDisplay ? "]" : ")",
        replacement: isDisplay ? "$$" : "$",
      };
      result += currentBlock.replacement;
      i += 2;
      continue;
    }

    result += line[i];
    i += 1;
  }

  return {
    line: result,
    state: { openBlock: currentBlock, inlineCodeDelimiterLength },
  };
}

export function normalizeLatexMathDelimiters(markdown: string): string {
  if (!/[\\][([\])]/.test(markdown)) {
    return markdown;
  }

  let insideFence = false;
  let mathState: DelimiterState = {
    openBlock: null,
    inlineCodeDelimiterLength: null,
  };

  return markdown
    .split("\n")
    .map((line) => {
      if (CODE_FENCE_RE.test(line) && !mathState.openBlock) {
        insideFence = !insideFence;
        return line;
      }
      if (
        insideFence ||
        (INDENTED_CODE_RE.test(line) && !mathState.openBlock)
      ) {
        return line;
      }
      const converted = convertLatexDelimitersInLine(line, mathState);
      mathState = converted.state;
      return converted.line;
    })
    .join("\n");
}

function hasUnescapedTexComment(line: string): boolean {
  for (let i = 0; i < line.length; i++) {
    if (line[i] !== "%") {
      continue;
    }

    let backslashCount = 0;
    for (let j = i - 1; j >= 0 && line[j] === "\\"; j--) {
      backslashCount += 1;
    }

    if (backslashCount % 2 === 0) {
      return true;
    }
  }

  return false;
}

function flattenDisplayMathBody(lines: string[]): string[] {
  if (lines.some(hasUnescapedTexComment)) {
    return lines;
  }

  return [lines.map((line) => line.trim()).join(" ")];
}

export function compactDisplayMathBlocks(markdown: string): string {
  if (!markdown.includes("$$")) {
    return markdown;
  }

  const output: string[] = [];
  let insideFence = false;
  let mathLines: string[] | null = null;

  for (const line of markdown.split("\n")) {
    if (CODE_FENCE_RE.test(line) && mathLines === null) {
      insideFence = !insideFence;
      output.push(line);
      continue;
    }

    if (insideFence || (INDENTED_CODE_RE.test(line) && mathLines === null)) {
      output.push(line);
      continue;
    }

    if (line.trim() === "$$") {
      if (mathLines === null) {
        mathLines = [];
      } else {
        const flattenedMathLines = flattenDisplayMathBody(mathLines);
        output.push("$$", ...flattenedMathLines, "$$");
        mathLines = null;
      }
      continue;
    }

    if (mathLines !== null) {
      mathLines.push(line);
      continue;
    }

    output.push(line);
  }

  if (mathLines !== null) {
    output.push("$$", ...mathLines);
  }

  return output.join("\n");
}

export function normalizeStreamdownMathMarkdown(markdown: string): string {
  return compactDisplayMathBlocks(normalizeLatexMathDelimiters(markdown));
}

export function preprocessStreamdownMarkdown(markdown: string): string {
  if (!MERMAID_BLOCK_HINT_RE.test(markdown) || !markdown.includes("-.->")) {
    return markdown;
  }

  return normalizeMermaidMarkdown(markdown);
}
