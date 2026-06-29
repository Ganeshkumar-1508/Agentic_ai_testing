/**
 * Log Storage Service
 * Persists run artifacts to agent_workspace/runs/ directory structure.
 */

import * as fs from 'fs';
import * as path from 'path';

// ─── Constants ────────────────────────────────────────────────────────────────

const RUNS_DIR = path.join(process.cwd(), 'agent_workspace', 'runs');

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LogFileEntry {
  path: string;
  type: 'file' | 'directory';
  mime?: string;
  size?: number;
  children?: LogFileEntry[];
}

// ─── Service ──────────────────────────────────────────────────────────────────

class LogStorageService {
  private ensureRunsDir(): void {
    if (!fs.existsSync(RUNS_DIR)) {
      fs.mkdirSync(RUNS_DIR, { recursive: true });
    }
  }

  private ensureRunDir(runId: string): string {
    this.ensureRunsDir();
    const runDir = path.join(RUNS_DIR, runId);
    if (!fs.existsSync(runDir)) {
      fs.mkdirSync(runDir, { recursive: true });
    }
    return runDir;
  }

  /** Get the base runs directory path */
  getRunsDir(): string {
    this.ensureRunsDir();
    return RUNS_DIR;
  }

  /** Get the path for a specific run */
  getRunDir(runId: string): string {
    return path.join(RUNS_DIR, runId);
  }

  /** Create all subdirectories for a new run */
  async initRunDir(runId: string): Promise<string> {
    const runDir = this.ensureRunDir(runId);

    // Create standard subdirectory structure
    const dirs = [
      path.join(runDir, 'research'),
      path.join(runDir, 'setup'),
      path.join(runDir, 'agents'),
      path.join(runDir, 'test-execution'),
    ];

    for (const d of dirs) {
      if (!fs.existsSync(d)) {
        fs.mkdirSync(d, { recursive: true });
      }
    }

    // Create timestamp file
    const timestamp = new Date().toISOString();
    fs.writeFileSync(
      path.join(runDir, 'timestamp.txt'),
      `Run started: ${timestamp}\n`,
      'utf-8',
    );

    return runDir;
  }

  /** Write content to a path within the run directory */
  async writeFile(
    runId: string,
    relativePath: string,
    content: string,
  ): Promise<string> {
    const runDir = this.ensureRunDir(runId);
    const fullPath = path.join(runDir, relativePath);

    // Ensure parent directory exists
    const parentDir = path.dirname(fullPath);
    if (!fs.existsSync(parentDir)) {
      fs.mkdirSync(parentDir, { recursive: true });
    }

    fs.writeFileSync(fullPath, content, 'utf-8');

    return fullPath;
  }

  /** Recursively read directory structure for the file explorer */
  async getFileTree(runId: string): Promise<LogFileEntry | null> {
    const runDir = path.join(RUNS_DIR, runId);
    if (!fs.existsSync(runDir)) return null;

    return this.buildTree(runDir, '');
  }

  /** Read a file's content from the run directory */
  async readFile(runId: string, relativePath: string): Promise<string | null> {
    const baseDir = path.resolve(RUNS_DIR, runId);
    const fullPath = path.resolve(baseDir, relativePath);
    if (!fullPath.startsWith(baseDir + path.sep)) return null;
    if (!fs.existsSync(fullPath)) return null;
    const content = fs.readFileSync(fullPath, 'utf-8');
    return content;
  }

  /** List all run directories with basic info */
  getRunsList(): Array<{ id: string; createdAt: Date }> {
    this.ensureRunsDir();
    const entries = fs.readdirSync(RUNS_DIR, { withFileTypes: true });
    const runs: Array<{ id: string; createdAt: Date }> = [];

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const stats = fs.statSync(path.join(RUNS_DIR, entry.name));
        runs.push({
          id: entry.name,
          createdAt: stats.birthtime,
        });
      }
    }

    // Sort newest first
    runs.sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
    return runs;
  }

  // ── Private Helpers ────────────────────────────────────────────────────

  private buildTree(dirPath: string, relativePath: string): LogFileEntry {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    const children: LogFileEntry[] = [];

    for (const entry of entries) {
      const childRelativePath = relativePath
        ? `${relativePath}/${entry.name}`
        : entry.name;
      const childFullPath = path.join(dirPath, entry.name);

      if (entry.isDirectory()) {
        children.push(this.buildTree(childFullPath, childRelativePath));
      } else {
        const stats = fs.statSync(childFullPath);
        children.push({
          path: childRelativePath,
          type: 'file',
          mime: this.getMimeType(entry.name),
          size: stats.size,
        });
      }
    }

    // Sort: directories first, then files, alphabetical
    children.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
      return a.path.localeCompare(b.path);
    });

    return {
      path: relativePath || '.',
      type: 'directory',
      children,
    };
  }

  private getMimeType(filename: string): string {
    const ext = path.extname(filename).toLowerCase();
    const mimeMap: Record<string, string> = {
      '.txt': 'text/plain',
      '.md': 'text/markdown',
      '.json': 'application/json',
      '.js': 'text/javascript',
      '.ts': 'text/typescript',
      '.py': 'text/x-python',
      '.html': 'text/html',
      '.css': 'text/css',
      '.log': 'text/plain',
      '.yaml': 'text/yaml',
      '.yml': 'text/yaml',
      '.xml': 'text/xml',
      '.toml': 'text/toml',
    };
    return mimeMap[ext] || 'application/octet-stream';
  }
}

export const logStorageService = new LogStorageService();
