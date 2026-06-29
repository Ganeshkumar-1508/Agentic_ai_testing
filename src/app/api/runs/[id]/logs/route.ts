import { NextRequest, NextResponse } from 'next/server';
import { logStorageService } from '@/lib/services/log-storage-service';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const tree = await logStorageService.getFileTree(id);
  if (!tree) {
    return NextResponse.json({ error: 'Run not found' }, { status: 404 });
  }
  return NextResponse.json({ tree });
}
