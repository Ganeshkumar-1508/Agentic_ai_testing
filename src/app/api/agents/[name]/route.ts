import { NextRequest, NextResponse } from "next/server";
import { api } from "@/lib/api/api-client";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  try {
    const agent = await api.get<any>(`/api/agents/${name}`);
    return NextResponse.json(agent);
  } catch {
    return NextResponse.json({ detail: "Agent not found" }, { status: 404 });
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  try {
    await api.delete(`/api/agents/${name}`);
    return NextResponse.json({ deleted: true });
  } catch {
    return NextResponse.json({ detail: "Agent not found" }, { status: 404 });
  }
}
