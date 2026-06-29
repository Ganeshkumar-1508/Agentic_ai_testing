import { NextRequest, NextResponse } from "next/server";
import { testPipeline } from "@/lib/react-test-generator/pipeline";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;
    if (!file) {
      return NextResponse.json({ error: "No file provided", code: "MISSING_FILE" }, { status: 400 });
    }

    const filename = file.name;
    const content = await file.text();

    const result = await testPipeline.runFullPipeline(filename, content);

    return NextResponse.json({
      sessionId: result.sessionId,
      componentName: result.componentName,
      analysis: result.analysis,
      generatedSource: result.generation?.generatedSource || "",
      execution: result.execution,
      warnings: [],
    });
  } catch (err: unknown) {
    const e = err as { error?: string; code?: string; message?: string };
    const message = e.error || e.message || "Pipeline failed";
    const code = e.code || "INTERNAL_ERROR";
    return NextResponse.json({ error: message, code }, { status: 422 });
  }
}
