import { existsSync, mkdirSync, writeFileSync, readFileSync, unlinkSync, rmdirSync, readdirSync } from 'fs';
import { join, extname, basename } from 'path';
import { ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES } from './constants';

export function validateFileType(filename: string): boolean {
  const ext = extname(filename).toLowerCase();
  return (ALLOWED_EXTENSIONS as readonly string[]).includes(ext);
}

export function validateFileSize(content: string | Buffer): boolean {
  const size = typeof content === 'string' ? Buffer.byteLength(content, 'utf-8') : content.length;
  return size <= MAX_FILE_SIZE_BYTES;
}

export function createSessionDir(sessionId: string, baseDir: string): string {
  const dir = join(baseDir, sessionId);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
  return dir;
}

export function writeComponentFile(sessionDir: string, filename: string, content: string): string {
  const filePath = join(sessionDir, filename);
  writeFileSync(filePath, content, 'utf-8');
  return filePath;
}

export function readComponentFile(filePath: string): string {
  return readFileSync(filePath, 'utf-8');
}

export function cleanSessionDir(sessionDir: string): void {
  if (!existsSync(sessionDir)) return;
  try {
    const files = readdirSync(sessionDir);
    for (const file of files) {
      const filePath = join(sessionDir, file);
      try { unlinkSync(filePath); } catch { /* ignore */ }
    }
    try { rmdirSync(sessionDir); } catch { /* ignore */ }
  } catch { /* ignore */ }
}

export function inferComponentName(filename: string): string {
  const name = basename(filename, extname(filename));
  // Convert kebab-case to PascalCase
  return name
    .split(/[-_]/)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join('');
}
