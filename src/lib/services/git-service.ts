/**
 * Git Service
 * Handles cloning and validating repos from GitHub, GitLab, Bitbucket.
 * Uses simple-git for Node.js operations.
 */

import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface RepoInfo {
  provider: 'github' | 'gitlab' | 'bitbucket';
  owner: string;
  repo: string;
  fullUrl: string;
}

export interface CloneResult {
  repoPath: string;
  repoInfo: RepoInfo;
  fileTree: string[];
  fileContents: Record<string, string>;
}

// ─── Service ──────────────────────────────────────────────────────────────────

class GitService {
  /** Parse a repo URL to extract provider, owner, and repo name */
  parseRepoUrl(url: string): RepoInfo | null {
    const patterns = [
      // HTTPS: https://github.com/owner/repo.git or https://gitlab.com/owner/repo
      {
        regex: /https?:\/\/(github|gitlab|bitbucket)\.(?:com|org)\/([\w.-]+)\/([\w.-]+?)(?:\.git|\/)?$/,
        map: (_m: RegExpExecArray) => ({ provider: _m[1] as RepoInfo['provider'], owner: _m[2], repo: _m[3] }),
      },
      // SSH: git@github.com:owner/repo.git
      {
        regex: /git@(github|gitlab|bitbucket)\.(?:com|org):([\w.-]+)\/([\w.-]+?)(?:\.git)?$/,
        map: (_m: RegExpExecArray) => ({ provider: _m[1] as RepoInfo['provider'], owner: _m[2], repo: _m[3] }),
      },
      // Short: owner/repo
      {
        regex: /^([\w.-]+)\/([\w.-]+)$/,
        map: (_m: RegExpExecArray) => ({ provider: 'github' as RepoInfo['provider'], owner: _m[1], repo: _m[2] }),
      },
    ];

    for (const { regex, map } of patterns) {
      const match = regex.exec(url.trim());
      if (match) {
        const { provider, owner, repo } = map(match);
        const fullUrl = `https://${provider}.com/${owner}/${repo}`;
        return { provider, owner, repo, fullUrl };
      }
    }
    return null;
  }

  /** Validate that a repo URL is reachable (lightweight check) */
  async validateRepo(url: string): Promise<{ valid: boolean; error?: string; repoInfo?: RepoInfo }> {
    const repoInfo = this.parseRepoUrl(url);
    if (!repoInfo) {
      return { valid: false, error: 'Invalid repository URL format. Use: owner/repo, https://github.com/owner/repo, or git@...' };
    }

    // Attempt git ls-remote as a lightweight reachability check
    try {
      execSync(`git ls-remote --heads "${repoInfo.fullUrl}"`, {
        timeout: 15_000,
        stdio: 'pipe',
        shell: process.platform === 'win32' ? (process.env.ComSpec || 'cmd.exe') : '/bin/sh',
      });
      return { valid: true, repoInfo };
    } catch {
      // Repo might be private or unreachable — still allow it to proceed
      return {
        valid: true,
        repoInfo,
        error: 'Could not verify reachability (repo may be private or unreachable). Clone will be attempted anyway.',
      };
    }
  }

  /** Clone a repository to a temporary directory with shallow depth */
  async cloneRepo(url: string, targetDir?: string): Promise<CloneResult> {
    const repoInfo = this.parseRepoUrl(url);
    if (!repoInfo) throw new Error(`Invalid repository URL: ${url}`);

    const cloneDir = targetDir || fs.mkdtempSync(path.join(os.tmpdir(), 'testai-clone-'));
    const repoPath = path.join(cloneDir, repoInfo.repo);

    // Shallow clone for speed
    execSync(
      `git clone --depth 1 "${repoInfo.fullUrl}" "${repoPath}"`,
      { timeout: 120_000, stdio: 'pipe', cwd: cloneDir },
    );

    // Collect file tree
    const fileTree = this.walkDir(repoPath);
    const fileContents: Record<string, string> = {};

    // Read key config files and a sample of source files
    const importantFiles = fileTree.filter((f) =>
      /package\.json|requirements\.txt|pyproject\.toml|^\.env|Dockerfile|docker-compose|composer\.json|Gemfile|Cargo\.toml|go\.mod|build\.gradle|pom\.xml|tsconfig\.json|next\.config|vite\.config|\.csproj|Podfile|pubspec\.yaml|mix\.exs/.test(path.basename(f)),
    );

    // Also read a sample of source files (up to 20)
    const sourceFiles = fileTree
      .filter((f) => /\.(ts|tsx|js|jsx|py|go|rs|rb|php|java|kt|swift|dart|ex)$/i.test(f))
      .slice(0, 20);

    const filesToRead = [...new Set([...importantFiles, ...sourceFiles])];
    for (const filePath of filesToRead) {
      try {
        const fullPath = path.join(repoPath, filePath);
        if (fs.statSync(fullPath).size < 100_000) {
          // Skip files > 100KB
          fileContents[filePath] = fs.readFileSync(fullPath, 'utf-8');
        }
      } catch {
        // Skip unreadable files
      }
    }

    return { repoPath, repoInfo, fileTree, fileContents };
  }

  /** Recursively walk a directory and collect relative file paths */
  private walkDir(dirPath: string, prefix = ''): string[] {
    const results: string[] = [];

    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dirPath, { withFileTypes: true });
    } catch {
      return results;
    }

    for (const entry of entries) {
      // Skip hidden directories, node_modules, venv, .git, etc.
      if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === 'venv' || entry.name === '__pycache__') {
        continue;
      }

      const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;

      if (entry.isDirectory()) {
        results.push(...this.walkDir(path.join(dirPath, entry.name), relativePath));
      } else {
        results.push(relativePath);
      }
    }

    return results;
  }

  /** Clean up a cloned repository */
  cleanupRepo(cloneDir: string): void {
    try {
      fs.rmSync(cloneDir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup
    }
  }
}

export const gitService = new GitService();
