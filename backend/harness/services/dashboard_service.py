"""Dashboard widget service — one method per widget, independently testable.

Extracted from api/routers/dashboard_widgets.py (was 895 lines of inline SQL).
Each method is read-only and returns safe defaults (empty lists, zeros) when
underlying tables are empty or unavailable.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _iso(dt: Any) -> str | None:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _pct_change(arr: list[float]) -> float:
    if len(arr) < 2:
        return 0.0
    mid = len(arr) // 2
    first = sum(arr[:mid]) / max(mid, 1)
    last = sum(arr[mid:]) / max(len(arr) - mid, 1)
    if first == 0:
        return 0.0 if last == 0 else 100.0
    return round((last - first) / first * 100, 1)


class DashboardWidgetService:
    def __init__(self, db: Any):
        self._db = db

    async def get_self_healing(self, limit: int = 8) -> dict:
        try:
            rows = await self._db.fetch(
                "SELECT id, test_name, old_locator, new_locator, strategy, "
                "confidence, passed, created_at "
                "FROM healing_log ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        except Exception as e:
            logger.warning("self_healing: healing_log unavailable: %s", e)
            return {"active": False, "success_rate": 0.0, "events": [], "count": 0}

        events = [{
            "id": str(r["id"]),
            "test_name": r["test_name"] or "",
            "old_locator": r["old_locator"] or "",
            "new_locator": r["new_locator"] or "",
            "strategy": r["strategy"] or "",
            "confidence": float(r["confidence"] or 0),
            "passed": bool(r["passed"]),
            "created_at": _iso(r["created_at"]),
        } for r in rows]

        try:
            stats = await self._db.fetchrow(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN passed = true THEN 1 ELSE 0 END) as succeeded "
                "FROM healing_log WHERE created_at >= NOW() - INTERVAL '30 days'"
            )
            total = int(stats["total"] or 0) if stats else 0
            succeeded = int(stats["succeeded"] or 0) if stats else 0
            success_rate = round(succeeded / total * 100, 1) if total > 0 else 0.0
        except Exception:
            total = len(events)
            succeeded = sum(1 for e in events if e["passed"])
            success_rate = round(succeeded / total * 100, 1) if total > 0 else 0.0

        return {
            "active": total > 0,
            "success_rate": success_rate,
            "total_attempts": total,
            "succeeded": succeeded,
            "events": events,
            "count": len(events),
        }

    async def get_logs(self, type: str = "console", limit: int = 20) -> dict:
        type_filters = []
        if type == "console":
            type_filters = ["tool.execution.started", "tool.execution.completed", "llmcall.started", "llmcall.completed", "reasoning"]

            type_filters = ["tool.execution.started", "tool.execution.completed"]

            type_filters = ["error", "tool.execution.started", "tool.execution.completed"]

            type_filters = ["tool.execution.started", "tool.execution.completed"]
        elif type == "errors":
            type_filters = ["error", "tool.execution.started", "tool.execution.completed"]
        if not type_filters:
            type_filters = ["tool.execution.started", "tool.execution.completed"]

        placeholders = ", ".join(f"${i+1}" for i in range(len(type_filters)))
        query = (
            f"SELECT id, event_type, event_data, agent_id, created_at "
            f"FROM trace_events WHERE event_type IN ({placeholders}) "
            f"ORDER BY created_at DESC LIMIT ${len(type_filters)+1}"
        )
        try:
            rows = await self._db.fetch(query, *type_filters, limit)
        except Exception as e:
            logger.warning("logs_widget: trace_events unavailable: %s", e)
            return {"type": type, "events": [], "count": 0}

        entries = []
        for r in rows:
            raw_data = r.get("event_data")
            data: dict = {}
            if raw_data:
                try:
                    data = json.loads(raw_data) if isinstance(raw_data, str) else (raw_data or {})
                except (json.JSONDecodeError, TypeError):
                    data = {}
            inner = data.get("data", data) if isinstance(data, dict) else {}
            msg = self._format_log_message(r["event_type"], inner, type)
            level = self._log_level(r["event_type"], type)
            entries.append({
                "id": str(r["id"]),
                "time": r["created_at"].strftime("%H:%M:%S") if r.get("created_at") else "",
                "level": level,
                "event_type": r["event_type"],
                "agent_id": r.get("agent_id") or "",
                "message": msg,
                "created_at": _iso(r["created_at"]),
            })

        return {"type": type, "events": entries, "count": len(entries)}

    def _format_log_message(self, event_type: str, inner: dict, panel: str) -> str:
        if event_type == "error":
            return f"Tool error: {inner.get('error', 'unknown')[:200]}"
        if event_type in ("llmcall.started", "llmcall.completed"):
            return f"LLM call: model={inner.get('model', '?')}, tokens={inner.get('total_tokens', '?')}"
        if event_type == "reasoning":
            return f"Reasoning: {(inner.get('content_preview') or '')[:160]}"
        if event_type in ("tool.execution.started", "tool.execution.completed"):
            return f"Tool: {inner.get('name', '?')}"
        return f"{event_type}: {json.dumps(inner)[:160]}"

    def _log_level(self, event_type: str, panel: str) -> str:
        if panel == "errors":
            return "ERR"
        if event_type == "error":
            return "ERR"
        if event_type == "reasoning":
            return "INFO"
        if "llm" in event_type:
            return "INFO"
        return "INFO"

    async def get_provider_failover(self, days: int = 7) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        routing = []
        total_calls = 0
        try:
            rows = await self._db.fetch(
                "SELECT model, COUNT(*) as calls, SUM(estimated_cost_usd) as cost "
                "FROM token_usage WHERE timestamp >= $1 "
                "GROUP BY model ORDER BY calls DESC LIMIT 10",
                since,
            )
            total_calls = sum(int(r["calls"] or 0) for r in rows)
            for r in rows:
                calls = int(r["calls"] or 0)
                routing.append({
                    "model": r["model"] or "unknown",
                    "calls": calls,
                    "pct": round(calls / total_calls * 100, 1) if total_calls > 0 else 0,
                    "cost": round(float(r["cost"] or 0), 4),
                })
        except Exception as e:
            logger.warning("provider_failover: token_usage query failed: %s", e)

        open_providers = []
        last_failover = None
        try:
            ev_rows = await self._db.fetch(
                "SELECT provider, event_type, message, created_at FROM provider_events "
                "WHERE created_at >= $1 ORDER BY created_at DESC LIMIT 50",
                since,
            )
            per_provider = defaultdict(int)
            for ev in ev_rows:
                per_provider[ev["provider"]] += 1
                if ev["event_type"] in ("circuit_open", "failover"):
                    if ev["provider"] not in open_providers:
                        open_providers.append(ev["provider"])
            if ev_rows:
                first_failover = next((e for e in ev_rows if e["event_type"] == "failover"), None)
                if first_failover:
                    last_failover = {
                        "provider": first_failover["provider"],
                        "message": first_failover["message"] or "",
                        "at": _iso(first_failover["created_at"]),
                    }
        except Exception as e:
            logger.warning("provider_failover: provider_events unavailable: %s", e)

        return {
            "circuit_state": "open" if open_providers else "closed",
            "open_providers": open_providers,
            "open_count": len(open_providers),
            "last_failover": last_failover,
            "routing": routing,
            "total_calls": total_calls,
            "days": days,
        }

    async def get_defect_prediction(self, limit: int = 8) -> dict:
        try:
            from harness.defect_prediction import compute_risk_scores
            result = await compute_risk_scores(self._db, days=30)
        except Exception as e:
            logger.warning("defect_prediction: compute_risk_scores failed: %s", e)
            return {"modules": [], "high_risk_count": 0, "total_modules": 0}

        modules = result.get("modules", [])[:limit]
        for m in modules:
            m["badge"] = m.get("severity", "low")
        return {
            "modules": modules,
            "high_risk_count": result.get("high_risk_count", 0),
            "medium_risk_count": result.get("medium_risk_count", 0),
            "total_modules": result.get("total_modules", 0),
        }

    async def get_rca_clusters(self, days: int = 30) -> dict:
        try:
            from harness.rca import get_rca_summary
            result = await get_rca_summary(self._db, days=days)
        except Exception as e:
            logger.warning("rca_clusters: get_rca_summary failed: %s", e)
            return {
                "total_failures": 0, "defect_count": 0, "flake_count": 0,
                "cluster_count": 0, "top_defects": [], "top_flakes": [],
            }
        return {
            "total_failures": result.get("total_failures", 0),
            "defect_count": result.get("defect_count", 0),
            "flake_count": result.get("flake_count", 0),
            "cluster_count": result.get("cluster_count", 0),
            "top_defects": result.get("top_defects", []),
            "top_flakes": result.get("top_flakes", []),
            "days": days,
        }

    async def get_traceability(self) -> dict:
        by_type = {}
        try:
            rows = await self._db.fetch(
                "SELECT test_type, status, COUNT(*) as count "
                "FROM test_cases GROUP BY test_type, status"
            )
            for r in rows:
                ttype = r["test_type"] or "unknown"
                by_type.setdefault(ttype, {"total": 0, "passed": 0, "failed": 0, "pending": 0})
                by_type[ttype]["total"] += int(r["count"] or 0)
                s = r["status"] or "unknown"
                if s in by_type[ttype]:
                    by_type[ttype][s] += int(r["count"] or 0)
        except Exception as e:
            logger.warning("traceability: test_cases query failed: %s", e)

        req_total = 0
        linked_pct = 0.0
        try:
            req_total_row = await self._db.fetchrow(
                "SELECT COUNT(*) as total FROM requirements WHERE status = 'active'"
            )
            req_total = int(req_total_row["total"] or 0) if req_total_row else 0
            linked_row = await self._db.fetchrow(
                "SELECT COUNT(DISTINCT rl.requirement_id) as linked "
                "FROM requirement_links rl JOIN test_cases tc ON tc.id = rl.test_case_id "
                "WHERE tc.status = 'passed'"
            )
            linked = int(linked_row["linked"] or 0) if linked_row else 0
            linked_pct = round(linked / req_total * 100, 1) if req_total > 0 else 0.0
        except Exception as e:
            logger.warning("traceability: requirements query failed: %s", e)

        return {"by_type": by_type, "total_requirements": req_total, "linked_pct": linked_pct}

    async def get_cost_by_model(self, days: int = 30) -> dict:
        try:
            rows = await self._db.fetch(
                "SELECT model, COUNT(DISTINCT session_id) as session_count, "
                "SUM(estimated_cost_usd) as total_cost "
                "FROM token_usage "
                "WHERE timestamp >= NOW() - ($1 || ' days')::interval "
                "GROUP BY model ORDER BY total_cost DESC",
                str(days),
            )
            models = []
            total = 0.0
            for r in rows:
                cost = float(r["total_cost"] or 0)
                total += cost
                models.append({
                    "model": r["model"] or "unknown",
                    "session_count": int(r["session_count"] or 0),
                    "total_cost": round(cost, 4),
                })
            for m in models:
                m["pct"] = round(m["total_cost"] / total * 100, 1) if total > 0 else 0
            budget_remaining = max(0.0, 50.0 - total)
            return {
                "models": models,
                "total_cost": round(total, 4),
                "budget_total": 50.0,
                "budget_remaining": round(budget_remaining, 2),
                "budget_pct_used": round(total / 50.0 * 100, 1) if total > 0 else 0.0,
                "days": days,
            }
        except Exception as e:
            logger.warning("cost_by_model: token_usage unavailable: %s", e)
            return {
                "models": [], "total_cost": 0.0, "budget_total": 50.0,
                "budget_remaining": 50.0, "budget_pct_used": 0.0, "days": days,
            }

    async def get_token_heatmap(self, days: int = 7) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        grid = [[0, 0, 0] for _ in range(7)]
        day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        total_tokens = 0
        peak = {"tokens": 0, "day": "", "bucket": ""}
        try:
            rows = await self._db.fetch(
                "SELECT timestamp, (input_tokens + output_tokens) as tokens "
                "FROM token_usage WHERE timestamp >= $1",
                since,
            )
        except Exception as e:
            logger.warning("token_heatmap: token_usage unavailable: %s", e)
            rows = []

        for r in rows:
            ts = r["timestamp"]
            if not ts:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            weekday = ts.weekday()
            hour = ts.hour
            bucket = 0 if hour < 12 else (1 if hour < 18 else 2)
            tokens = int(r["tokens"] or 0)
            grid[weekday][bucket] += tokens
            total_tokens += tokens
            if tokens > peak["tokens"]:
                peak = {
                    "tokens": tokens,
                    "day": day_labels[weekday],
                    "bucket": ["AM", "PM", "Eve"][bucket],
                }

        return {
            "grid": grid, "labels": day_labels, "row_labels": ["AM", "PM", "Eve"],
            "total_tokens": total_tokens, "peak": peak, "days": days,
        }

    async def get_coverage_gaps(self, threshold: float = 80.0) -> dict:
        try:
            row = await self._db.fetchrow(
                "SELECT report_data, created_at FROM coverage_reports "
                "WHERE report_data IS NOT NULL ORDER BY created_at DESC LIMIT 1"
            )
        except Exception as e:
            logger.warning("coverage_gaps: coverage_reports unavailable: %s", e)
            return {"files": [], "threshold": threshold, "total_files": 0, "below_count": 0}

        if not row or not row.get("report_data"):
            return {"files": [], "threshold": threshold, "total_files": 0, "below_count": 0}

        raw = row["report_data"]
        report = raw if isinstance(raw, dict) else {}
        if not report:
            try:
                report = json.loads(raw) if isinstance(raw, str) else {}
            except (json.JSONDecodeError, TypeError):
                report = {}

        files_dict = report.get("files", {}) if isinstance(report, dict) else {}
        if not isinstance(files_dict, dict):
            return {"files": [], "threshold": threshold, "total_files": 0, "below_count": 0}

        entries = []
        for path, fdata in files_dict.items():
            if not isinstance(fdata, dict):
                continue
            pct = fdata.get("percent", fdata.get("line_coverage"))
            if not isinstance(pct, (int, float)):
                continue
            if pct >= threshold:
                continue
            entries.append({
                "file": path,
                "coverage_pct": round(float(pct), 1),
                "lines_covered": fdata.get("covered_lines"),
                "lines_total": fdata.get("total_lines"),
            })

        entries.sort(key=lambda e: (e["coverage_pct"], e["file"]))
        return {
            "files": entries[:20], "threshold": threshold,
            "total_files": len(files_dict), "below_count": len(entries),
            "report_timestamp": _iso(row.get("created_at")),
        }

    async def get_analytics_30d(self, days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        bucket_rows = []
        try:
            rows = await self._db.fetch(
                "SELECT DATE(created_at) as day, "
                "COUNT(*) as total, "
                "SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed, "
                "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed "
                "FROM test_results WHERE created_at >= $1 "
                "GROUP BY day ORDER BY day",
                since,
            )
            bucket_rows = [dict(r) for r in rows]
        except Exception as e:
            logger.warning("analytics_30d: test_results unavailable: %s", e)

        tests_run = sum(int(r.get("total") or 0) for r in bucket_rows)
        total_passed = sum(int(r.get("passed") or 0) for r in bucket_rows)
        pass_rate = round(total_passed / max(tests_run, 1) * 100, 1)

        flaky_row = await self._db.fetchrow(
            "SELECT COUNT(*) as c FROM flaky_tests WHERE flaky_score > 30"
        )
        flaky_count = int(flaky_row["c"] or 0) if flaky_row else 0
        flaky_rate = round(flaky_count / max(tests_run, 1) * 100, 1)

        spark_tests = [int(r.get("total") or 0) for r in bucket_rows]
        spark_pass_rate = [
            round((int(r.get("passed") or 0) / max(int(r.get("total") or 0), 1)) * 100, 1)
            for r in bucket_rows
        ]
        spark_flaky = [flaky_rate] * len(bucket_rows)

        return {
            "tests_run": tests_run, "pass_rate": pass_rate,
            "flaky_rate": flaky_rate, "flaky_count": flaky_count,
            "spark_tests": spark_tests, "spark_pass_rate": spark_pass_rate,
            "spark_flaky": spark_flaky,
            "change_tests_pct": _pct_change([float(x) for x in spark_tests]),
            "change_pass_pct": _pct_change(spark_pass_rate),
            "change_flaky_pct": _pct_change(spark_flaky),
            "days": days, "days_with_data": len(bucket_rows),
        }

    async def get_quick_actions(self) -> dict:
        try:
            failed = await self._db.fetchrow(
                "SELECT COUNT(*) as c FROM test_results WHERE status = 'failed' "
                "AND created_at >= NOW() - INTERVAL '24 hours'"
            )
            failed_count = int(failed["c"] or 0) if failed else 0
        except Exception:
            failed_count = 0

        try:
            pending = await self._db.fetchrow(
                "SELECT COUNT(*) as c FROM approval_queue WHERE status = 'pending'"
            )
            pending_approvals = int(pending["c"] or 0) if pending else 0
        except Exception:
            try:
                pending = await self._db.fetchrow(
                    "SELECT COUNT(*) as c FROM sessions WHERE status = 'awaiting_approval'"
                )
                pending_approvals = int(pending["c"] or 0) if pending else 0
            except Exception:
                pending_approvals = 0

        try:
            flaky = await self._db.fetchrow(
                "SELECT COUNT(*) as c FROM flaky_tests WHERE flaky_score >= 70"
            )
            high_risk_flaky = int(flaky["c"] or 0) if flaky else 0
        except Exception:
            high_risk_flaky = 0

        return {
            "failed_rerun_count": failed_count,
            "pending_approvals": pending_approvals,
            "high_risk_flaky": high_risk_flaky,
            "watch_mode_default": True,
        }

    async def get_coverage(self, days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        line_pct = 0.0
        branch_pct = 0.0
        last_updated = None
        sparkline = []
        change_pct = 0.0

        try:
            latest = await self._db.fetchrow(
                "SELECT line_coverage, branch_coverage, created_at "
                "FROM coverage_reports ORDER BY created_at DESC LIMIT 1"
            )
            if latest:
                line_pct = round(float(latest["line_coverage"] or 0), 1)
                branch_pct = round(float(latest["branch_coverage"] or 0), 1)
                last_updated = _iso(latest["created_at"])

            day_rows = await self._db.fetch(
                "SELECT DATE(created_at) as day, line_coverage, created_at "
                "FROM coverage_reports WHERE created_at >= $1 ORDER BY created_at DESC",
                since,
            )
            by_day = {}
            for r in day_rows:
                d = r["day"]
                if d not in by_day:
                    by_day[d] = {
                        "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                        "line_pct": round(float(r["line_coverage"] or 0), 1),
                    }
            for i in range(days):
                d = (now - timedelta(days=days - 1 - i)).date()
                entry = by_day.get(d)
                sparkline.append({
                    "date": d.isoformat(),
                    "line_pct": entry["line_pct"] if entry else 0.0,
                })

            non_zero = [s["line_pct"] for s in sparkline if s["line_pct"] > 0]
            if len(non_zero) >= 2:
                mid = len(non_zero) // 2
                first = sum(non_zero[:mid]) / max(mid, 1)
                last = sum(non_zero[mid:]) / max(len(non_zero) - mid, 1)
                if first > 0:
                    change_pct = round((last - first) / first * 100, 1)
        except Exception as e:
            logger.warning("coverage: coverage_reports unavailable: %s", e)

        untested_requirements = 0
        try:
            row = await self._db.fetchrow(
                "SELECT COUNT(*) as c FROM requirements r "
                "WHERE r.status = 'active' "
                "AND NOT EXISTS (SELECT 1 FROM requirement_links rl WHERE rl.requirement_id = r.id)"
            )
            untested_requirements = int(row["c"] or 0) if row else 0
        except Exception as e:
            logger.warning("coverage: requirements query failed: %s", e)

        return {
            "line_pct": line_pct, "branch_pct": branch_pct,
            "sparkline": sparkline, "change_pct": change_pct,
            "untested_requirements": untested_requirements,
            "last_updated": last_updated, "days": days,
        }

    async def get_sprint_trends(self, sprints: int = 5) -> dict:
        try:
            from harness.sprint_trends import get_sprint_trends
            return await get_sprint_trends(self._db, sprints=sprints)
        except Exception as e:
            logger.warning("sprint_trends: get_sprint_trends failed: %s", e)
            return {"sprints": [], "alerts": [], "alert_count": 0}

    async def get_notifications(self, limit: int = 8) -> dict:
        try:
            rows = await self._db.fetch(
                "SELECT id, channel, subject, body, status, source, run_id, created_at, delivered_at "
                "FROM notifications ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        except Exception as e:
            logger.warning("notifications: notifications unavailable: %s", e)
            return {"items": [], "unread": 0, "count": 0}

        items = [{
            "id": r["id"],
            "channel": r["channel"] or "system",
            "subject": r["subject"] or "",
            "body": (r["body"] or "")[:200],
            "status": r["status"] or "pending",
            "source": r["source"] or "",
            "run_id": r["run_id"] or "",
            "created_at": _iso(r["created_at"]),
            "delivered_at": _iso(r["delivered_at"]),
        } for r in rows]
        return {"items": items, "unread": len(items), "count": len(items)}

    async def get_system_health(self) -> dict:
        database = await self._check_database()
        queue = await self._check_queue()
        sessions = await self._check_sessions()
        pipeline = await self._check_pipeline()
        agents = await self._check_agents()
        containers = await self._check_containers()
        return {
            "database": database, "queue": queue, "sessions": sessions,
            "pipeline": pipeline, "agents": agents, "containers": containers,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _check_database(self) -> dict:
        started = datetime.now(timezone.utc)
        try:
            await self._db.fetchrow("SELECT 1 as ok")
            latency_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1)
            return {"status": "healthy", "detail": "Connected", "latency_ms": latency_ms}
        except Exception as e:
            logger.warning("system_health: database check failed: %s", e)
            return {"status": "down", "detail": "Unreachable", "latency_ms": None}

    async def _check_queue(self) -> dict:
        try:
            approvals = await self._db.fetchrow(
                "SELECT COUNT(*) as c FROM approval_queue WHERE status = 'pending'"
            )
            awaiting = await self._db.fetchrow(
                "SELECT COUNT(*) as c FROM sessions WHERE status = 'awaiting_approval'"
            )
            pending = (int(approvals["c"] or 0) if approvals else 0) + (int(awaiting["c"] or 0) if awaiting else 0)
            status = "warn" if pending > 10 else "healthy"
            return {"status": status, "detail": f"{pending} pending", "count": pending}
        except Exception as e:
            logger.warning("system_health: queue check failed: %s", e)
            return {"status": "healthy", "detail": "0 pending", "count": 0}

    async def _check_sessions(self) -> dict:
        try:
            row = await self._db.fetchrow(
                "SELECT COUNT(*) as c FROM sessions WHERE status = 'running'"
            )
            active = int(row["c"] or 0) if row else 0
            status = "healthy" if active < 50 else "warn"
            return {"status": status, "detail": f"{active} active", "count": active}
        except Exception as e:
            logger.warning("system_health: sessions check failed: %s", e)
            return {"status": "healthy", "detail": "0 active", "count": 0}

    async def _check_pipeline(self) -> dict:
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            row = await self._db.fetchrow(
                "SELECT SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed, "
                "SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running "
                "FROM pipeline_runs WHERE created_at >= $1",
                since,
            )
            failed = int(row["failed"] or 0) if row else 0
            running = int(row["running"] or 0) if row else 0
            if failed > 5:
                return {"status": "down", "detail": f"{failed} failed in 1h", "running": running}
            if failed > 0:
                return {"status": "warn", "detail": f"{failed} failed in 1h", "running": running}
            return {"status": "healthy", "detail": "Healthy", "running": running}
        except Exception as e:
            logger.warning("system_health: pipeline check failed: %s", e)
            return {"status": "healthy", "detail": "Healthy", "running": 0}

    async def _check_agents(self) -> dict:
        try:
            from harness.tools.delegate_task import active_subagents
            n = len(active_subagents())
        except Exception:
            n = 0
        return {"status": "healthy", "detail": f"{n} active", "count": n}

    async def _check_containers(self) -> dict:
        try:
            row = await self._db.fetchrow(
                "SELECT SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running, "
                "COUNT(*) as total FROM sandbox_metrics"
            )
            running = int(row["running"] or 0) if row else 0
            total = int(row["total"] or 0) if row else 0
            if total == 0:
                return {"status": "healthy", "detail": "0 running", "running": 0, "total": 0}
            if running == total:
                return {"status": "healthy", "detail": f"All {total} running", "running": running, "total": total}
            return {"status": "warn", "detail": f"{running}/{total} running", "running": running, "total": total}
        except Exception as e:
            logger.warning("system_health: containers check failed: %s", e)
            return {"status": "healthy", "detail": "0 running", "running": 0, "total": 0}
