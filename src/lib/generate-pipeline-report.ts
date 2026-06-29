export interface ReportRun {
  id: string;
  status: string;
  requirements?: string | null;
  createdAt: string;
  completedAt?: string | null;
  duration: number;
  testCount: number;
  passedCount: number;
  failedCount: number;
  skippedCount: number;
}

export interface ReportEvent {
  type: string;
  data: Record<string, unknown>;
  createdAt?: string;
}

export interface ReportTest {
  testName: string;
  status: string;
  durationMs: number;
  error?: string;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br>");
}

export function generatePipelineReport(run: ReportRun, events: ReportEvent[], tests: ReportTest[]): string {
  const passed = run.passedCount;
  const failed = run.failedCount;
  const total = run.testCount;
  const passRate = total > 0 ? Math.round((passed / total) * 100) : 0;
  const durationStr = run.duration >= 60000
    ? `${Math.floor(run.duration / 60000)}m ${Math.round((run.duration % 60000) / 1000)}s`
    : run.duration >= 1000
    ? `${(run.duration / 1000).toFixed(1)}s`
    : `${run.duration}ms`;

  const toolCalls = events.filter((e) =>
    ["ToolExecutionStarted", "ToolExecutionCompleted", "tool_calls", "tool_result"].includes(e.type)
  );
  const errors = events.filter((e) => e.type === "error");
  const reasoningCount = events.filter((e) => e.type === "reasoning").length;
  const totalTokens = events
    .filter((e) => e.type === "metrics")
    .reduce((s, e) => s + ((e.data as any).total_tokens || 0), 0);
  const cost = events
    .filter((e) => e.type === "metrics")
    .reduce((s, e) => s + ((e.data as any).estimated_cost_usd || 0), 0);

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Report — ${escapeHtml(run.id.slice(0, 12))}</title>
<style>
  body { font-family: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0b; color: #e4e4e7; margin: 0; padding: 0; }
  .container { max-width: 960px; margin: 0 auto; padding: 40px 24px; }
  h1 { font-size: 24px; font-weight: 600; letter-spacing: -0.02em; margin: 0 0 4px; }
  h2 { font-size: 16px; font-weight: 600; margin: 32px 0 16px; letter-spacing: -0.01em; }
  h3 { font-size: 14px; font-weight: 500; margin: 0 0 8px; color: #a1a1aa; }
  .meta { color: #71717a; font-size: 13px; margin-bottom: 32px; }
  .meta span { margin-right: 16px; }
  .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 32px; }
  .stat-card { background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 16px; }
  .stat-label { font-size: 11px; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
  .stat-value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .stat-value.green { color: #34d399; }
  .stat-value.red { color: #f87171; }
  .stat-value.zinc { color: #e4e4e7; }
  .stat-value.amber { color: #fbbf24; }
  .event { padding: 8px 12px; margin-bottom: 4px; border-radius: 8px; font-size: 13px; font-family: 'Geist Mono', 'SF Mono', monospace; line-height: 1.5; }
  .event-reasoning { background: rgba(251, 191, 36, 0.04); border-left: 2px solid rgba(251, 191, 36, 0.2); color: #a1a1aa; font-style: italic; }
  .event-tool { background: rgba(52, 211, 153, 0.04); border-left: 2px solid rgba(52, 211, 153, 0.2); color: #34d399; }
  .event-error { background: rgba(248, 113, 113, 0.04); border-left: 2px solid rgba(248, 113, 113, 0.2); color: #f87171; }
  .event-done { background: rgba(52, 211, 153, 0.06); border-left: 2px solid rgba(52, 211, 153, 0.3); color: #34d399; font-weight: 600; }
  .event-metrics { font-size: 11px; color: #71717a; padding: 4px 12px; }
  .event-info { color: #71717a; padding: 4px 12px; }
  .event-token { color: #a1a1aa; padding: 4px 12px; font-size: 12px; }
  .event-label { font-weight: 500; margin-right: 8px; opacity: 0.5; }
  .test-row { display: flex; align-items: center; padding: 8px 12px; border-bottom: 1px solid #27272a; font-size: 13px; }
  .test-row:last-child { border-bottom: none; }
  .test-status { width: 6px; height: 6px; border-radius: 50%; margin-right: 10px; flex-shrink: 0; }
  .test-status.passed { background: #34d399; }
  .test-status.failed { background: #f87171; }
  .test-status.skipped { background: #71717a; }
  .test-name { flex: 1; }
  .test-duration { color: #71717a; font-size: 11px; font-family: 'Geist Mono', 'SF Mono', monospace; }
  .section { background: #18181b; border: 1px solid #27272a; border-radius: 16px; padding: 20px; margin-bottom: 24px; }
  pre { margin: 0; white-space: pre-wrap; word-break: break-all; }
  a { color: #34d399; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
  .badge.completed { background: rgba(52, 211, 153, 0.1); color: #34d399; }
  .badge.failed { background: rgba(248, 113, 113, 0.1); color: #f87171; }
  .badge.running { background: rgba(59, 130, 246, 0.1); color: #60a5fa; }
  .req-block { background: #09090b; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.6; color: #a1a1aa; margin-top: 8px; }
  @media (max-width: 640px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
</head>
<body>
<div class="container">
  <h1>Pipeline Report</h1>
  <div class="meta">
    <span>ID: ${escapeHtml(run.id)}</span>
    <span>Status: <span class="badge ${run.status}">${escapeHtml(run.status)}</span></span>
    <span>Created: ${new Date(run.createdAt).toLocaleString()}</span>
    ${run.completedAt ? `<span>Completed: ${new Date(run.completedAt).toLocaleString()}</span>` : ""}
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Duration</div>
      <div class="stat-value zinc">${escapeHtml(durationStr)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Tests</div>
      <div class="stat-value zinc">${total}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Pass Rate</div>
      <div class="stat-value green">${passRate}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Cost</div>
      <div class="stat-value amber">$${cost.toFixed(4)}</div>
    </div>
  </div>

  ${run.requirements ? `
  <div class="section">
    <h3>Requirements</h3>
    <div class="req-block">${escapeHtml(run.requirements)}</div>
  </div>` : ""}

  <div class="section">
    <h3>Summary</h3>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px;">
      <div><span style="color:#71717a;">Passed</span><br><span style="font-size:20px;font-weight:600;color:#34d399;">${passed}</span></div>
      <div><span style="color:#71717a;">Failed</span><br><span style="font-size:20px;font-weight:600;color:#f87171;">${failed}</span></div>
      <div><span style="color:#71717a;">Skipped</span><br><span style="font-size:20px;font-weight:600;color:#71717a;">${run.skippedCount}</span></div>
    </div>
    <div style="margin-top:16px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
      <div><span style="color:#71717a;">Tool Calls</span><br><span style="font-size:20px;font-weight:600;">${toolCalls.length}</span></div>
      <div><span style="color:#71717a;">Reasoning Blocks</span><br><span style="font-size:20px;font-weight:600;">${reasoningCount}</span></div>
      <div><span style="color:#71717a;">Errors</span><br><span style="font-size:20px;font-weight:600;${errors.length > 0 ? 'color:#f87171;' : ''}">${errors.length}</span></div>
    </div>
    <div style="margin-top:16px;">
      <span style="color:#71717a;">Total Tokens</span><br>
      <span style="font-size:20px;font-weight:600;">${totalTokens.toLocaleString()}</span>
      ${cost > 0 ? `<span style="color:#71717a;font-size:13px;margin-left:16px;">$${cost.toFixed(4)} total cost</span>` : ""}
    </div>
  </div>

  ${tests.length > 0 ? `
  <div class="section">
    <h3>Test Results (${tests.length})</h3>
    ${tests.map((t) => `
    <div class="test-row">
      <div class="test-status ${t.status}"></div>
      <div class="test-name">${escapeHtml(t.testName)}</div>
      <div class="test-duration">${t.durationMs ? (t.durationMs >= 1000 ? (t.durationMs / 1000).toFixed(1) + 's' : t.durationMs + 'ms') : '—'}</div>
    </div>
    ${t.error ? `<div style="font-size:11px;color:#f87171;font-family:'Geist Mono', 'SF Mono', monospace;padding:0 12px 8px 28px;">${escapeHtml(t.error.slice(0, 200))}</div>` : ""}
    `).join("")}
  </div>` : ""}

  <div class="section">
    <h3>Pipeline Events (${events.length})</h3>
    ${events.map((ev) => {
      const d = ev.data || {};
      switch (ev.type) {
        case "reasoning":
          return '<div class="event event-reasoning"><span class="event-label">[reasoning]</span>' + escapeHtml(String(d.content || "").slice(0, 300)) + '</div>';
        case "tool_calls":
        case "ToolExecutionStarted":
        case "ToolExecutionCompleted":
        case "tool_result":
          const name = (d as any).tool_name || (d as any).name || (d as any).calls?.[0]?.function?.name || ev.type;
          return '<div class="event event-tool"><span class="event-label">[' + ev.type + ']</span>' + escapeHtml(String(name)) + '</div>';
        case "error":
          return '<div class="event event-error"><span class="event-label">[error]</span>' + escapeHtml(String((d as any).message || "Unknown error")) + '</div>';
        case "done":
          return '<div class="event event-done">Pipeline completed</div>';
        case "metrics":
          const tokens = (d as any).total_tokens || 0;
          const cst = (d as any).estimated_cost_usd || 0;
          return '<div class="event event-metrics">' + tokens.toLocaleString() + ' tokens · $' + cst.toFixed(4) + '</div>';
        case "token":
          const content = String(d.content || "").slice(0, 200);
          if (!content) return '';
          return '<div class="event event-token">' + escapeHtml(content) + '</div>';
        case "mode":
        case "pipeline:start":
          return '<div class="event event-info"><span class="event-label">[' + ev.type + ']</span></div>';
        default:
          return '';
      }
    }).filter(Boolean).join("")}
  </div>

  <div style="text-align:center;padding:32px 0;color:#52525b;font-size:12px;">
    Generated by TestAI · ${new Date().toLocaleString()}
  </div>
</div>
</body>
</html>`;
}
