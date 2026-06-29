"""Load testing — generates and executes k6 performance tests from OpenAPI specs."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def generate_k6_script(openapi_spec: dict[str, Any], test_type: str = "stress", vu_count: int = 10, duration_sec: int = 60) -> str:
    """Generate a k6 load test script from an OpenAPI spec."""
    paths = openapi_spec.get("paths", {})
    endpoints = []
    for path, methods in paths.items():
        for method in ("get", "post", "put", "delete", "patch"):
            if method in methods:
                endpoints.append({"method": method.upper(), "path": path, "summary": methods[method].get("summary", "")})

    stages = {
        "soak": f"{{duration: '{duration_sec}s', target: {vu_count}}}",
        "stress": f"{{duration: '2m', target: {vu_count * 2}}}, {{duration: '5m', target: {vu_count}}}, {{duration: '2m', target: 0}}",
        "spike": f"{{duration: '30s', target: 0}}, {{duration: '10s', target: {vu_count * 10}}}, {{duration: '1m', target: 0}}",
    }.get(test_type, f"{{duration: '{duration_sec}s', target: {vu_count}}}")

    endpoint_checks = "\n".join(
        f'  http_{e["method"].lower()}("{e["path"]}", {{\n'
        f'    tags: {{ name: "{e["method"]} {e["path"]}" }},\n'
        f"  }});"
        for e in endpoints[:20]
    )

    return f"""
import http from 'k6/http';
import {{ check, sleep }} from 'k6';
import {{ Rate, Trend }} from 'k6/metrics';

const failures = new Rate('failed_requests');
const latency = new Trend('latency');

export let options = {{
  stages: [{stages}],
  thresholds: {{
    http_req_duration: ['p(95)<2000', 'p(99)<5000'],
    http_req_failed: ['rate<0.05'],
  }},
}};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:3000';

export default function () {{
  const payload = JSON.stringify({{}});
  const params = {{
    headers: {{ 'Content-Type': 'application/json' }},
    timeout: '10s',
  }};

{endpoint_checks}

  sleep(1);
}}
"""


async def run_load_test(openapi_spec: dict[str, Any], test_type: str = "stress", vu_count: int = 10, duration_sec: int = 60) -> dict[str, Any]:
    """Run a k6 load test and return results."""
    script = generate_k6_script(openapi_spec, test_type, vu_count, duration_sec)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        result = subprocess.run(
            ["k6", "run", "--out", "json=/tmp/k6_results.json", script_path],
            capture_output=True, text=True, timeout=duration_sec + 60,
        )
    except FileNotFoundError:
        logger.warning("k6 not installed. Install from https://k6.io/docs/getting-started/installation/")
        return {"error": "k6 not installed", "status": "skipped"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "status": "timeout"}
    finally:
        Path(script_path).unlink(missing_ok=True)

    # Parse results
    results_path = Path("/tmp/k6_results.json")
    metrics = {"http_req_duration": [], "http_req_failed": []}
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            try:
                entry = json.loads(line)
                if entry.get("type") == "Point" and entry.get("metric") in metrics:
                    metrics[entry["metric"]].append(entry["data"]["value"])
            except (json.JSONDecodeError, KeyError):
                pass
        results_path.unlink(missing_ok=True)

    durations = sorted(metrics["http_req_duration"])
    total = len(durations)
    p50 = durations[int(total * 0.5)] if total else 0
    p95 = durations[int(total * 0.95)] if total else 0
    p99 = durations[int(total * 0.99)] if total else 0
    failures_count = sum(1 for v in metrics["http_req_failed"] if v == 1)

    return {
        "status": "completed",
        "test_type": test_type,
        "virtual_users": vu_count,
        "duration_seconds": duration_sec,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "error_rate": round(failures_count / max(total, 1), 4),
        "throughput_rps": round(total / max(duration_sec, 1), 2),
        "total_requests": total,
    }
