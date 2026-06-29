import { NextRequest, NextResponse } from 'next/server';
import { logStorageService } from '@/lib/services/log-storage-service';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string; path: string[] }> },
) {
  const { id, path: pathSegments } = await params;
  const relativePath = pathSegments.join('/');
  const content = await logStorageService.readFile(id, relativePath);
  if (content === null) {
    return NextResponse.json({ error: 'File not found' }, { status: 404 });
  }
  return NextResponse.json({ content });
}
