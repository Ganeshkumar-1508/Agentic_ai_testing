const fs = require('fs');
const path = require('path');

const rootDir = 'C:\\Users\\AswinPremnathChandra\\Documents\\testai-production';
const srcApp = path.join(rootDir, 'src', 'app');
const srcComponents = path.join(rootDir, 'src', 'components');

const hookNames = [
  'useState', 'useEffect', 'useContext', 'useReducer', 'useCallback', 'useMemo', 'useRef',
  'useLayoutEffect', 'useDeferredValue', 'useTransition', 'useId', 'useSyncExternalStore',
  'useInsertionEffect', 'useQuery', 'useMutation', 'useQueryClient', 'useRouter'
];
const hookPattern = new RegExp(`\\b(${hookNames.join('|')})\\s*\\(`, 'g');

function findUseClientFiles(dir) {
  const results = [];
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        results.push(...findUseClientFiles(fullPath));
      } else if (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) {
        const content = fs.readFileSync(fullPath, 'utf-8');
        if (content.startsWith('"use client"') || content.startsWith("'use client'")) {
          results.push(fullPath);
        }
      }
    }
  } catch (e) { /* ignore */ }
  return results;
}

function analyzeFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const issues = [];
  let hasFragileImport = false;
  let hasEarlyReturn = false;
  let hasConditionalHooks = false;

  // Check for next/dist imports
  if (/from\s+["']next\/dist\//.test(content)) {
    hasFragileImport = true;
    issues.push('Imports from next/dist/ (internal Next.js module that could break)');
  }

  // Find all hook call positions (line number, character index)
  const hookCalls = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let match;
    while ((match = hookPattern.exec(line)) !== null) {
      hookCalls.push({ line: i, col: match.index, hook: match[1] });
    }
  }

  if (hookCalls.length === 0) {
    return {
      file: filePath,
      issues: [],
      has_fragile_import: hasFragileImport,
      has_early_return_before_hooks: false,
      has_conditional_hooks: false,
      is_clean: !hasFragileImport
    };
  }

  const firstHookLine = hookCalls[0].line;

  // Find function boundaries by tracking brace depth
  // We need to find which function body the first hook belongs to
  let fnEntryDepth = -1;
  let fnEntryLine = -1;
  let depth = 0;

  for (let i = 0; i <= firstHookLine && i < lines.length; i++) {
    const line = lines[i];
    for (const ch of line) {
      if (ch === '{') {
        depth++;
        // Check if this brace opens a function/component body
        if (fnEntryDepth < 0) {
          fnEntryDepth = depth;
          fnEntryLine = i;
        }
      }
      if (ch === '}') {
        depth--;
        // If we close back to entry level, reset
        if (depth < fnEntryDepth && fnEntryDepth > 0) {
          // This hook is in a nested scope... let's be more careful
        }
      }
    }
  }

  // Better approach: find function declaration lines and track opening braces
  // Look for patterns like: function Component, const Component = (..., export default function
  depth = 0;
  const functionEntries = [];
  let lastBraceLine = -1;

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    
    // Count brace changes
    for (const ch of lines[i]) {
      if (ch === '{') {
        depth++;
        // Check if this brace starts a new function scope
        const prevLine = i > 0 ? lines[i-1].trim() : '';
        const currLine = lines[i].trim();
        
        // Detect function component/hook entry points by looking at previous line
        const isFunctionEntry = 
          /^(export\s+)?(default\s+)?function\s+\w+\s*\(/.test(lines[i]) ||
          /^(export\s+)?default\s+function\s+\w+\s*\(/.test(lines[i]) ||
          (currLine === '{' && /=>\s*$/.test(prevLine)) ||
          (currLine === '{' && /\breturn\s+\(/.test(prevLine)) ||
          (/\bconst\s+\w+\s*=\s*\(/.test(lines[i]) && lines[i].includes('=>')) ||
          (/\bconst\s+\w+\s*=\s*\(/.test(lines[i]) && lines[i].includes('{'));
        
        if (isFunctionEntry) {
          functionEntries.push({ depth: depth, line: i });
        } else if (currLine === '{' && prevLine.length > 0 && !prevLine.startsWith('import') && !prevLine.startsWith('//') && !prevLine.startsWith('/*')) {
          // Could be a function body too
        }
      }
      if (ch === '}') {
        depth--;
      }
    }
  }

  // Now check for early returns before the first hook call
  // We need to find which function body contains the first hook
  functionEntries.sort((a, b) => b.line - a.line);
  const containingFn = functionEntries.find(fe => fe.line <= firstHookLine);

  if (containingFn) {
    const fnStart = containingFn.line;
    const fnDepth = containingFn.depth;
    
    // Scan from function start + 1 to first hook for return statements
    let localDepth = 0;
    let inScope = false;
    for (let i = fnStart; i < firstHookLine && i < lines.length; i++) {
      const line = lines[i];
      for (const ch of line) {
        if (ch === '{') { localDepth++; inScope = true; }
        if (ch === '}') { localDepth--; }
      }
      
      // We want returns at depth >= 1 (inside function body)
      const trimmed = line.trim();
      if (inScope && (trimmed.startsWith('return ') || trimmed === 'return;' || trimmed.startsWith('return(') || /^return\s+</.test(trimmed))) {
        hasEarlyReturn = true;
        issues.push(`Early return at line ${i+1} before hook calls (would cause React error #300)`);
      }
    }
  } else {
    // Fallback: just scan file for returns before first hook
    // But be careful not to catch returns in other functions
    for (let i = 0; i < firstHookLine && i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (trimmed.startsWith('import ')) continue;
      if (trimmed.startsWith('"use client"') || trimmed.startsWith("'use client'")) continue;
      if (trimmed.startsWith('//') || trimmed.startsWith('/*') || trimmed.startsWith('*')) continue;
      if (trimmed.startsWith('export type') || trimmed.startsWith('type ') || trimmed.startsWith('interface ')) continue;
      if (trimmed.startsWith('export {')) continue;
      if (trimmed.startsWith('}')) continue;
      
      if ((trimmed.startsWith('return ') || trimmed === 'return;' || trimmed.startsWith('return(')) && 
          !trimmed.includes('=>')) {  // exclude arrow function returns
        hasEarlyReturn = true;
        issues.push(`Early return at line ${i+1} before hook calls (would cause React error #300)`);
      }
    }
  }

  // Check for conditional hooks
  // Approach: track if/else/ternary blocks and check if hooks appear inside them
  let braceDepth = 0;
  const conditionalStack = []; // stack of { type, line, depth }
  let inTypeDef = false;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    
    // Skip type definitions and interfaces
    if (trimmed.startsWith('type ') || trimmed.startsWith('interface ')) {
      inTypeDef = true;
      continue;
    }
    if (inTypeDef && trimmed.includes('}')) {
      inTypeDef = false;
      continue;
    }
    if (inTypeDef) continue;
    
    // Detect conditional openings
    if (/\bif\s*\(/.test(trimmed) || /\belse\s+if\s*\(/.test(trimmed)) {
      conditionalStack.push({ type: 'if', line: i, depth: braceDepth, pending: true });
    } else if (/^else\s*\{/.test(trimmed) || /^else\s*$/.test(trimmed)) {
      conditionalStack.push({ type: 'else', line: i, depth: braceDepth, pending: true });
    } else if (/\bcatch\s*\(/.test(trimmed)) {
      conditionalStack.push({ type: 'catch', line: i, depth: braceDepth, pending: true });
    } else if (/\bswitch\s*\(/.test(trimmed)) {
      conditionalStack.push({ type: 'switch', line: i, depth: braceDepth, pending: true });
    } else if (/\bcase\s+/.test(trimmed) && !trimmed.startsWith('//')) {
      // case is conditional
    }
    
    // Track braces
    for (const ch of line) {
      if (ch === '{') {
        braceDepth++;
        // Mark any pending conditionals as active
        for (const cond of conditionalStack) {
          if (cond.pending) {
            cond.activeDepth = braceDepth;
            cond.pending = false;
          }
        }
      }
      if (ch === '}') {
        braceDepth--;
        // Close conditionals that end at this depth
        while (conditionalStack.length > 0) {
          const last = conditionalStack[conditionalStack.length - 1];
          if (!last.pending && last.activeDepth !== undefined && braceDepth < last.activeDepth) {
            conditionalStack.pop();
          } else {
            break;
          }
        }
      }
    }
    
    // Check if this line contains a hook call and is inside a conditional
    if (conditionalStack.length > 0 && hookPattern.test(trimmed) && !trimmed.startsWith('//')) {
      // Reset lastIndex
      hookPattern.lastIndex = 0;
      if (hookPattern.test(trimmed)) {
        hasConditionalHooks = true;
        const cond = conditionalStack[conditionalStack.length - 1];
        issues.push(`Hook called inside ${cond.type} block (conditional) at line ${i+1}, conditional started at line ${cond.line+1}`);
      }
      hookPattern.lastIndex = 0;
    }
    
    // Also check for ternary hooks on same line
    if (/\?[^?]*\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(/.test(trimmed)) {
      hasConditionalHooks = true;
      const issueStr = `Hook called inside ternary condition at line ${i+1}`;
      if (!issues.includes(issueStr)) issues.push(issueStr);
    }
    
    // Check for && short-circuit with hooks
    if (/&&\s*\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(/.test(trimmed)) {
      hasConditionalHooks = true;
      const issueStr = `Hook called after && (short-circuit conditional) at line ${i+1}`;
      if (!issues.includes(issueStr)) issues.push(issueStr);
    }
  }

  const isClean = issues.length === 0;

  return {
    file: filePath,
    issues: issues,
    has_fragile_import: hasFragileImport,
    has_early_return_before_hooks: hasEarlyReturn,
    has_conditional_hooks: hasConditionalHooks,
    is_clean: isClean
  };
}

// Main
const appFiles = findUseClientFiles(srcApp);
const compFiles = findUseClientFiles(srcComponents);
const allFiles = [...new Set([...appFiles, ...compFiles])].sort();

const results = allFiles.map(f => analyzeFile(f));
console.log(JSON.stringify(results, null, 2));
