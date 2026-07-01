from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["sandbox"])


class ReapRequest(BaseModel):
    max_age_hours: float = 2


class _SandboxManager:
    """Lightweight wrapper around backend_factory for legacy sandbox router endpoints.

    Provides the ``list_sandboxes``, ``get_env``, ``destroy_env``, ``snapshot``,
    ``restore``, and ``list_snapshots`` interface that the rest of this module
    expects.  In the current architecture all session-level state lives on the
    per-session backend, so several of these methods are stubs or no-ops.
    """

    def __init__(self, factory):
        self._factory = factory

    def list_sandboxes(self):
        return []

    def get_env(self, session_id: str):
        return self._factory(session_id)

    def destroy_env(self, session_id: str):
        from harness.tools.docker_executor import destroy_container
        destroy_container(session_id)

    def snapshot(self, session_id: str, label: str = ""):
        return ""

    def restore(self, snapshot_id: str, session_id: str | None = None):
        return session_id or ""

    def list_snapshots(self, session_id: str | None = None):
        return []


def _manager(request: Request):
    factory = getattr(request.app.state, "backend_factory", None)
    if not factory:
        raise RuntimeError("Backend factory not initialised")
    return _SandboxManager(factory)


def _db(request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        raise RuntimeError("DB not initialised")
    return db


async def _env(request: Request, session_id: str):
    mgr = _manager(request)
    env = mgr.get_env(session_id)
    if not env:
        raise RuntimeError(f"Sandbox {session_id} not found")
    return env


@router.get("/sandbox/exec-containers")
async def list_exec_containers(request: Request):
    try:
        _manager(request)
        return {"containers": []}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/sandbox/exec-containers/{session_id}")
async def destroy_exec_container(request: Request, session_id: str):
    try:
        from harness.tools.docker_executor import destroy_container
        ok = destroy_container(session_id)
        if not ok:
            return JSONResponse(status_code=404, content={"error": f"Container for session {session_id} not found"})
        return {"status": "destroyed", "session_id": session_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/sandbox/exec-containers/reap")
async def reap_exec_containers(
    request: Request,
    body: ReapRequest | None = Body(None),
):
    try:
        from harness.backends.docker import find_docker
        docker = find_docker()
        if not docker:
            return JSONResponse(status_code=503, content={"error": "Docker not available"})
        hours = body.max_age_hours if body else 2
        qp = request.query_params.get("max_age_hours")
        if qp is not None:
            try:
                hours = int(qp)
            except (TypeError, ValueError):
                pass
        result = subprocess.run(
            [docker, "ps", "-a", "--filter", "label=testai-agent=1",
             "--filter", "status=exited", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=15,
        )
        ids = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        reaped = []
        for cid in ids:
            subprocess.run([docker, "rm", "-f", cid], capture_output=True, timeout=15)
            reaped.append(cid[:12])
        return {"reaped": len(reaped), "names": reaped}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/list")
async def list_sandboxes(request: Request):
    try:
        _manager(request)
        return {"sandboxes": [], "message": "Sandbox listing migrated to per-session backends"}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})


@router.get("/sandbox/volumes")
async def list_workspace_volumes(request: Request):
    """List all testai-ws-* workspace volumes with size, created_at, and in-use state.
    The sanitized volume name suffix maps back to a human-readable repo identifier
    (session_id or repo_url, depending on how the volume was keyed)."""
    try:
        from harness.backends.docker import find_docker
        import datetime

        docker = find_docker() or "docker"
        VOLUME_NAME_PREFIX = "testai-ws-"

        ls = subprocess.run(
            [docker, "volume", "ls", "--filter", f"name={VOLUME_NAME_PREFIX}",
             "--format", "{{.Name}}\t{{.Driver}}"],
            capture_output=True, text=True, timeout=15,
        )

        used_names: set[str] = set()
        ps = subprocess.run(  # noqa: S603
            [docker, "ps", "-a", "--filter", "name=testai-sandbox-",
             "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        if ps.returncode == 0 and ps.stdout.strip():
            used_names.update(n.strip() for n in ps.stdout.strip().split("\n") if n.strip())

        ps2 = subprocess.run(  # noqa: S603
            [docker, "ps", "-a", "--format", "{{.Names}}\t{{.Mounts}}"],
            capture_output=True, text=True, timeout=10,
        )
        in_use: set[str] = set()
        if ps2.returncode == 0 and ps2.stdout.strip():
            for line in ps2.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                _name, mounts = line.split("\t", 1)
                for m in mounts.split(","):
                    m = m.strip()
                    if m.startswith(VOLUME_NAME_PREFIX):
                        in_use.add(m)

        out: list[dict[str, Any]] = []
        for line in ls.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            vol_name = parts[0]
            seg = vol_name[len(VOLUME_NAME_PREFIX):]
            inspect = subprocess.run(  # noqa: S603
                [docker, "volume", "inspect", vol_name,
                 "--format", "{{.CreatedAt}}\t{{.Mountpoint}}"],
                capture_output=True, text=True, timeout=10,
            )
            created_at = ""
            if inspect.returncode == 0 and inspect.stdout.strip():
                created_at = inspect.stdout.split("\t")[0].strip()
            created_iso = ""
            if created_at:
                try:
                    created_iso = datetime.datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    ).isoformat()
                except Exception:
                    created_iso = created_at

            out.append({
                "name": vol_name,
                "segment": seg,
                "created_at": created_iso,
                "in_use": vol_name in in_use,
            })

        out.sort(key=lambda v: v.get("created_at") or "", reverse=True)
        return {"volumes": out, "prefix": VOLUME_NAME_PREFIX, "reap_after_hours": 24 * 7}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/sandbox/volumes/{volume_name}")
async def destroy_workspace_volume(request: Request, volume_name: str):
    """Manually destroy a workspace volume. Refuses if the volume name is not
    in the testai-ws-* prefix or if a container is currently using it."""
    try:
        from harness.backends.docker import find_docker
        VOLUME_NAME_PREFIX = "testai-ws-"
        if not volume_name.startswith(VOLUME_NAME_PREFIX):
            return JSONResponse(
                status_code=400,
                content={"error": f"Refusing to destroy volume outside {VOLUME_NAME_PREFIX}*"},
            )
        docker = find_docker() or "docker"

        # Refuse if in use
        ps = subprocess.run(  # noqa: S603
            [docker, "ps", "-a", "--format", "{{.Names}}\t{{.Mounts}}"],
            capture_output=True, text=True, timeout=10,
        )
        if ps.returncode == 0 and ps.stdout.strip():
            for line in ps.stdout.strip().split("\n"):
                if not line.strip() or "\t" not in line:
                    continue
                _name, mounts = line.split("\t", 1)
                if volume_name in (m.strip() for m in mounts.split(",")):
                    return JSONResponse(
                        status_code=409,
                        content={"error": f"Volume {volume_name} is in use by a running container; destroy that container first."},
                    )

        rm = subprocess.run(  # noqa: S603
            [docker, "volume", "rm", "-f", volume_name],
            capture_output=True, text=True, timeout=30,
        )
        if rm.returncode != 0:
            return JSONResponse(
                status_code=404,
                content={"error": f"Failed to destroy volume: {rm.stderr.strip() or 'not found'}"},
            )
        return {"status": "destroyed", "volume": volume_name}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/metrics")
async def aggregate_sandbox_metrics(request: Request):
    """Aggregate CPU, memory, disk across all running sandboxes. Used by KPI strip."""
    try:
        sandboxes = _manager(request).list_sandboxes()
        _ = sandboxes  # keep reference (currently always empty, migrated to per-session backends)
        total_cpu = 0.0
        total_mem_used = 0
        total_mem_cap = 0
        total_disk_used = 0
        total_disk_cap = 0
        count = 0
        for sb in sandboxes:
            sid = sb.get("session_id", "")
            if not sid:
                continue
            try:
                env = await _env(request, sid)
                result = await env.run("cat /proc/meminfo && echo '---DISK---' && df -h /workspace && echo '---CPU---' && nproc && echo '---LOAD---' && cat /proc/loadavg", timeout=10)
                mem_total = 0; mem_avail = 0; cpu_count = 1; load_1 = 0
                disk_used = 0; disk_total = 0
                for line in result.stdout.splitlines():
                    if "MemTotal:" in line: mem_total = int(line.split()[1]) // 1024
                    if "MemAvailable:" in line: mem_avail = int(line.split()[1]) // 1024
                    m = re.match(r"(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", line)
                    if m and m.group(6) == "/workspace":
                        disk_total = int(m.group(2)) if m.group(2).isdigit() else 0
                        disk_used = int(m.group(3)) if m.group(3).isdigit() else 0
                    if line.strip().isdigit(): cpu_count = int(line.strip())
                    parts = line.strip().split()
                    if len(parts) == 5 and all(p.replace(".", "").isdigit() for p in parts[:3]):
                        load_1 = float(parts[0])
                total_cpu += round((load_1 / cpu_count) * 100, 1) if cpu_count else 0
                total_mem_used += mem_total - mem_avail
                total_mem_cap += mem_total
                total_disk_used += disk_used
                total_disk_cap += disk_total
                count += 1
            except Exception:
                pass
        return {
            "sandbox_count": len(sandboxes),
            "running_count": count,
            "avg_cpu_percent": round(total_cpu / max(count, 1), 1),
            "memory_used_mb": total_mem_used,
            "memory_total_mb": total_mem_cap,
            "disk_used_mb": total_disk_used,
            "disk_total_mb": total_disk_cap,
        }
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})


@router.get("/sandbox/{session_id}/resources")
async def get_sandbox_resources(request: Request, session_id: str):
    try:
        env = await _env(request, session_id)
        result = await env.run("cat /proc/meminfo && echo '---DISK---' && df -h /workspace && echo '---CPU---' && nproc && echo '---LOAD---' && cat /proc/loadavg", timeout=10)
        mem_total = 0
        mem_avail = 0
        disk_used_mb = 0
        disk_total_mb = 0
        cpu_count = 1
        load_1 = 0
        for line in result.stdout.splitlines():
            if "MemTotal:" in line:
                mem_total = int(line.split()[1]) // 1024
            if "MemAvailable:" in line:
                mem_avail = int(line.split()[1]) // 1024
            m = re.match(r"(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", line)
            if m and m.group(6) == "/workspace":
                disk_total_mb = int(m.group(2)) if m.group(2).isdigit() else 0
                disk_used_mb = int(m.group(3)) if m.group(3).isdigit() else 0
            if line.strip().isdigit():
                cpu_count = int(line.strip())
            parts = line.strip().split()
            if len(parts) == 5 and all(p.replace(".", "").isdigit() for p in parts[:3]):
                load_1 = float(parts[0])
        mem_used_mb = mem_total - mem_avail
        return {
            "cpu_percent": round((load_1 / cpu_count) * 100, 1) if cpu_count else 0,
            "memory_used_mb": mem_used_mb,
            "memory_total_mb": mem_total,
            "disk_used_mb": disk_used_mb,
            "disk_total_mb": disk_total_mb,
            "network_kbps": 0,
        }
    except RuntimeError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/{session_id}/ports")
async def get_sandbox_ports(request: Request, session_id: str):
    try:
        env = await _env(request, session_id)
        result = await env.run("ss -tlnp 2>/dev/null | tail -n +2 | awk '{print $4}' | grep -v '127.0.0.1' | grep -oP ':(\\d+)$' | sort -u || netstat -tlnp 2>/dev/null | grep LISTEN | awk '{print $4}' | grep -oP ':(\\d+)$' | sort -u", timeout=5)
        ports = []
        for line in result.stdout.splitlines():
            line = line.strip().replace(":", "")
            if line.isdigit():
                port = int(line)
                label = {3000: "preview", 9321: "coverage", 5173: "vite", 4173: "preview"}.get(port, "")
                ports.append({"container_port": port, "host_port": port, "label": label})
        return {"ports": ports}
    except RuntimeError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/{session_id}/dependencies")
async def get_sandbox_dependencies(request: Request, session_id: str):
    try:
        env = await _env(request, session_id)
        result = await env.run("pip list --format=json 2>/dev/null || echo 'PIP_NOT_FOUND'", timeout=15)
        deps = []
        if result.stdout.strip() != "PIP_NOT_FOUND":
            try:
                parsed = json.loads(result.stdout)
                deps = [{"name": p["name"], "version": p["version"]} for p in parsed[:30]]
            except json.JSONDecodeError:
                pass
        if not deps:
            result = await env.run("cat /workspace/package.json 2>/dev/null || echo '{}'", timeout=5)
            try:
                pkg = json.loads(result.stdout)
                deps = [{"name": k, "version": v.replace("^", "").replace("~", "")} for k, v in {**(pkg.get("dependencies", {}) or {}), **(pkg.get("devDependencies", {}) or {})}.items()][:30]
            except json.JSONDecodeError:
                pass
        count = len(deps)
        return {"dependencies": deps, "total_count": count}
    except RuntimeError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/{session_id}/flaky-tests")
async def get_flaky_tests(request: Request, session_id: str):
    try:
        db = _db(request)
        rows = await db.fetch(
            "SELECT test_name, COUNT(*) as total, "
            "SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed, "
            "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed "
            "FROM test_results WHERE run_id IN "
            "(SELECT id FROM pipeline_runs WHERE session_id = $1) "
            "GROUP BY test_name HAVING COUNT(*) > 1 ORDER BY total DESC",
            session_id,
        )
        flaky = []
        for row in rows:
            total = row["total"]
            passed = row["passed"]
            failed = row["failed"]
            score = round((min(passed, failed) / max(total, 1)) * 100, 1)
            if score > 15:
                flaky.append({
                    "test_name": row["test_name"],
                    "total_runs": total,
                    "pass_count": passed,
                    "fail_count": failed,
                    "flaky_score": score,
                    "is_quarantined": score > 50,
                })
        return {"flaky_tests": flaky}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/{session_id}/artifacts")
async def get_sandbox_artifacts(request: Request, session_id: str):
    try:
        env = await _env(request, session_id)
        result = await env.run(
            "find /workspace -maxdepth 3 -type f "
            r"\( -name 'coverage*.json' -o -name 'lcov*' -o -name 'test-report*' "
            r"-o -name 'junit*' -o -name 'results*.json' -o -name 'summary*.md' "
            r"-o -name '*.html' \) 2>/dev/null "
            "| head -20",
            timeout=5,
        )
        artifacts = []
        for fpath in result.stdout.splitlines():
            fpath = fpath.strip()
            if not fpath:
                continue
            name = os.path.basename(fpath)
            size_res = await env.run(f"stat --format='%s' '{fpath}' 2>/dev/null || echo 0", timeout=3)
            size_bytes = int(size_res.stdout.strip() or 0)
            ext = os.path.splitext(name)[1].lower()
            mime = {"json": "application/json", "html": "text/html", "md": "text/markdown", "xml": "application/xml", "txt": "text/plain", "info": "text/plain"}.get(ext.lstrip("."), "application/octet-stream")
            artifacts.append({"name": name, "path": fpath, "size_bytes": size_bytes, "mime_type": mime})
        return {"artifacts": artifacts}
    except RuntimeError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/{session_id}/events")
async def get_sandbox_events(request: Request, session_id: str):
    try:
        db = _db(request)
        rows = await db.fetch(
            "SELECT event_data FROM trace_events WHERE run_id IN "
            "(SELECT id FROM pipeline_runs WHERE (COALESCE(inputs::jsonb->>'session_id', '') = $1 OR workflow_id = $1)) "
            "ORDER BY created_at ASC LIMIT 200",
            session_id,
        )
        events = []
        for row in rows:
            try:
                data = json.loads(row["event_data"]) if isinstance(row["event_data"], str) else row["event_data"]
            except (json.JSONDecodeError, TypeError):
                data = row["event_data"] or {}
            event_type = data.get("event_type", "") or ""
            if event_type in ("tool:start", "tool.execution.started"):
                events.append({"type": "exec", "message": f"$ {data.get('name', 'tool')} {json.dumps(data.get('arguments', {}))[:80]}"})
            elif event_type in ("tool:end", "tool.execution.completed"):
                if data.get("success"):
                    events.append({"type": "pass", "message": f"{data.get('name')} completed", "detail": (data.get("output_preview") or "")[:100]})
                else:
                    events.append({"type": "fail", "message": f"{data.get('name')} failed", "detail": (data.get("output_preview") or "")[:100]})
            elif event_type in ("agent:start", "agent:end", "round:start", "round:end"):
                events.append({"type": "agent", "message": data.get("event_type", event_type)})
        return {"events": events}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/workspace/{session_id}")
async def get_workspace_tree(request: Request, session_id: str, path: str = "."):
    try:
        env = await _env(request, session_id)
        import shlex
        safe_path = shlex.quote(path)
        result = await env.run(
            f"find {safe_path} -maxdepth 2 -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | head -100",
            timeout=5,
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return {"session_id": session_id, "path": path, "files": files}
    except RuntimeError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/{session_id}/stream")
async def stream_sandbox_logs(request: Request, session_id: str):
    """SSE endpoint streaming real-time container logs (docker logs --follow).
    
    Lets the sandbox UI show live agent activity inside the container
    as commands execute — no polling needed.
    """
    from sse_starlette.sse import EventSourceResponse
    import subprocess as _sp

    mgr = getattr(request.app.state, "backend_factory", None)
    if not mgr:
        return JSONResponse(status_code=503, content={"error": "Backend factory not initialized"})
    cid = ""
    for sb in sandboxes:
        if sb.get("session_id") == session_id:
            cid = sb.get("container_id", "")
            break
    
    if not cid:
        return JSONResponse(status_code=404, content={"error": f"Sandbox {session_id} not found"})

    async def event_generator():
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "--follow", "--tail", "100", cid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                yield {"event": "log", "data": text}
        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@router.get("/sandbox/workspace/{session_id}/file")
async def read_workspace_file(request: Request, session_id: str, path: str):
    try:
        env = await _env(request, session_id)
        if not await env.file_exists(path):
            return JSONResponse(status_code=404, content={"error": f"File not found: {path}"})
        content = await env.read_file(path)
        return {"session_id": session_id, "path": path, "content": content, "size": len(content)}
    except RuntimeError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/workspace/{session_id}/archive")
async def download_workspace_archive(request: Request, session_id: str):
    try:
        env = await _env(request, session_id)
        result = await env.run("cd /workspace && tar czf /tmp/workspace.tar.gz . 2>/dev/null && wc -c < /tmp/workspace.tar.gz", timeout=30)
        size = int(result.stdout.strip() or 0)
        data_res = await env.run("cat /tmp/workspace.tar.gz | base64", timeout=30)
        import base64
        raw = base64.b64decode(data_res.stdout.strip())

        from fastapi.responses import StreamingResponse
        import io
        return StreamingResponse(
            iter([raw]),
            media_type="application/gzip",
            headers={"Content-Disposition": f"attachment; filename=sandbox-{session_id[:12]}.tar.gz", "Content-Length": str(size)},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/sandbox/{session_id}/exec")
async def execute_in_sandbox(request: Request, session_id: str):
    try:
        from harness.tools.docker_executor import DockerExecutorTool
        body = await request.json()
        command = body.get("command", "")
        if not command:
            return JSONResponse(status_code=400, content={"error": "command is required"})
        tool = DockerExecutorTool()
        result = await tool.run(command=command, _session_id=session_id, timeout=body.get("timeout", 60))
        return {
            "output": result.output,
            "success": result.success,
            "error": result.error,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/sandbox/{session_id}/exec/stream")
async def stream_exec_in_sandbox(request: Request, session_id: str):
    """SSE endpoint that runs a command and streams output in real-time."""
    from sse_starlette.sse import EventSourceResponse

    env = await _env(request, session_id)
    body = await request.json()
    command = body.get("command", "")
    if not command:
        return JSONResponse(status_code=400, content={"error": "command is required"})

    async def event_generator():
        try:
            proc = await asyncio.create_subprocess_shell(
                f"docker exec {env.container_id} sh -c {shlex.quote(command)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield {"event": "output", "data": line.decode("utf-8", errors="replace").rstrip()}
            rc = await proc.wait()
            yield {"event": "done", "data": str(rc)}
        except asyncio.CancelledError:
            yield {"event": "cancelled", "data": ""}
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@router.delete("/sandbox/{session_id}")
async def destroy_sandbox(request: Request, session_id: str):
    try:
        await _manager(request).destroy_env(session_id)
        return {"status": "destroyed", "session_id": session_id}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# C4.1 — SandboxSnapshot primitive (E2B / Daytona / Modal / Sprites pattern)
#
# The snapshot is an EXPOSED primitive the agent / orchestrator / UI
# invokes explicitly — no auto-snapshot. The HTTP routes below mirror
# the Python API on `SandboxManager.snapshot/restore/list_snapshots`
# so the frontend UI can drive them. Sync methods run in the FastAPI
# threadpool so they don't block the event loop on long docker commits.
# ---------------------------------------------------------------------------


@router.post("/sandbox/{session_id}/snapshot")
async def create_sandbox_snapshot(request: Request, session_id: str):
    """Commit a running sandbox's full state to a tagged Docker image.

    Body (optional): `{"label": "my-checkpoint"}`. The label is a
    free-form string the caller chooses; it is sanitized into a
    docker-tag-safe suffix and combined with `session_id[:12]` and
    a content-hash to form the unique snapshot_id. The original
    sandbox continues running — a snapshot is one-to-many.
    """
    label = ""
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        if isinstance(body, dict):
            label = str(body.get("label", "") or "")
    except Exception:
        label = ""
    try:
        mgr = _manager(request)
        # `snapshot()` is sync (docker commit is a subprocess) — run it
        # in the threadpool so the FastAPI event loop stays free for
        # other in-flight requests.
        import asyncio
        snapshot_id = await asyncio.get_event_loop().run_in_executor(
            None, mgr.snapshot, session_id, label
        )
        return {
            "status": "snapshotted",
            "session_id": session_id,
            "snapshot_id": snapshot_id,
            "label": label,
        }
    except KeyError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/sandbox/restore")
async def restore_sandbox_snapshot(request: Request):
    """Spawn a new sandbox from a snapshot image.

    Body: `{"snapshot_id": "testai-snapshot-...", "session_id": "optional"}`.
    If `session_id` is omitted, a stable `restored-<snapshot_id>` id
    is derived. Returns the new session_id so the caller can look up
    the running env via `/api/sandbox/{session_id}/resources`.
    """
    try:
        body = await request.json()
        snapshot_id = str(body.get("snapshot_id", "") or "").strip()
        session_id = body.get("session_id")
        if session_id is not None:
            session_id = str(session_id).strip() or None
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON body required: {snapshot_id, session_id?}"})
    if not snapshot_id:
        return JSONResponse(status_code=400, content={"error": "snapshot_id is required"})
    try:
        mgr = _manager(request)
        import asyncio
        new_session_id = await asyncio.get_event_loop().run_in_executor(
            None, lambda: mgr.restore(snapshot_id, session_id=session_id)
        )
        return {
            "status": "restored",
            "snapshot_id": snapshot_id,
            "session_id": new_session_id,
        }
    except (ValueError, RuntimeError) as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/{session_id}/snapshots")
async def list_sandbox_snapshots(request: Request, session_id: str):
    """List snapshot image tags for a single session.

    Optional query `?session_id=...` is implicit in the path. Pass
    an empty list to enumerate every snapshot in the local image
    cache; the underlying `list_snapshots(session_id=None)` returns
    all `testai-snapshot-*` tags.
    """
    try:
        mgr = _manager(request)
        import asyncio
        snapshots = await asyncio.get_event_loop().run_in_executor(
            None, mgr.list_snapshots, session_id
        )
        return {
            "session_id": session_id,
            "snapshots": snapshots,
            "count": len(snapshots),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sandbox/snapshots")
async def list_all_snapshots(request: Request):
    """List every TestAI snapshot image in the local Docker cache.

    The session-filtered version is `/sandbox/{session_id}/snapshots`.
    """
    try:
        mgr = _manager(request)
        import asyncio
        snapshots = await asyncio.get_event_loop().run_in_executor(
            None, mgr.list_snapshots, None
        )
        return {"snapshots": snapshots, "count": len(snapshots)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# WebSocket PTY endpoint — interactive terminal streaming
#
# Adapted from hermes-agent pty_bridge.py + web_server.py /api/pty.
# Spawns `docker exec -it container_id sh` behind a PTY so ANSI
# output streams to the browser (xterm.js) and keystrokes feed back in.
#
# Protocol:
#   Client → Server: raw keystroke bytes (UTF-8 encoded)
#   Client → Server: resize escape `\x1b[RESIZE:<cols>;<rows>]`
#   Server → Client: raw PTY output bytes (includes ANSI escape codes)
#
# POSIX-only: requires ptyprocess, fcntl, termios.
# Falls back to SSE-based streaming on Windows.
# ---------------------------------------------------------------------------

_PTY_READ_CHUNK_TIMEOUT = 0.2  # seconds between PTY read attempts
_RESIZE_RE = re.compile(rb"^\x1b\[RESIZE:(\d+);(\d+)\]$")


@router.websocket("/sandbox/{session_id}/pty")
async def pty_websocket(ws: WebSocket, session_id: str):
    """WebSocket endpoint for interactive terminal streaming.

    Connects to the sandbox container via PTY-backed docker exec.
    Streams ANSI output to the client and accepts keystroke input.
    """
    # Check PTY availability
    try:
        from harness.sandbox.pty_bridge import PtyBridge, PtyUnavailableError
    except ImportError:
        await ws.accept()
        await ws.send_text(
            "\r\n\x1b[31mPTY unavailable: ptyprocess package not installed.\x1b[0m\r\n"
        )
        await ws.close(code=1011)
        return

    if not PtyBridge.is_available():
        await ws.accept()
        await ws.send_text(
            "\r\n\x1b[31mPTY unavailable on this platform.\x1b[0m\r\n"
            "\x1b[33mUse WSL on Windows.\x1b[0m\r\n"
        )
        await ws.close(code=1011)
        return

    # Get container ID
    await ws.accept()
    try:
        mgr = _manager_from_ws(ws)
        env = mgr.get_env(session_id)
        container_id = env.container_id
    except Exception as e:
        await ws.send_text(f"\r\n\x1b[31mSandbox error: {e}\x1b[0m\r\n")
        await ws.close(code=1011)
        return

    # Spawn PTY: docker exec -it container_id sh
    try:
        bridge = PtyBridge.spawn(container_id)
    except PtyUnavailableError as e:
        await ws.send_text(f"\r\n\x1b[31mPTY spawn failed: {e}\x1b[0m\r\n")
        await ws.close(code=1011)
        return
    except (FileNotFoundError, OSError) as e:
        await ws.send_text(f"\r\n\x1b[31mPTY start failed: {e}\x1b[0m\r\n")
        await ws.close(code=1011)
        return

    loop = asyncio.get_running_loop()

    # Reader task: PTY master → WebSocket (bytes)
    async def pump_pty_to_ws():
        while True:
            chunk = await loop.run_in_executor(
                None, bridge.read, _PTY_READ_CHUNK_TIMEOUT
            )
            if chunk is None:  # EOF
                return
            if not chunk:  # no data this tick
                await asyncio.sleep(0)
                continue
            try:
                await ws.send_bytes(chunk)
            except Exception:
                return

    reader_task = asyncio.create_task(pump_pty_to_ws())

    # Writer loop: WebSocket → PTY master (bytes)
    try:
        while True:
            msg = await ws.receive()
            msg_type = msg.get("type")
            if msg_type == "websocket.disconnect":
                break
            raw = msg.get("bytes")
            if raw is None:
                text = msg.get("text")
                raw = text.encode("utf-8") if isinstance(text, str) else b""
            if not raw:
                continue

            # Resize escape: consumed locally, never written to PTY
            match = _RESIZE_RE.match(raw)
            if match and match.end() == len(raw):
                cols = int(match.group(1))
                rows = int(match.group(2))
                bridge.resize(cols=cols, rows=rows)
                continue

            bridge.write(raw)
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):
            pass
        bridge.close()


def _manager_from_ws(ws: WebSocket):
    """Get sandbox manager from WebSocket app state."""
    factory = getattr(ws.app.state, "backend_factory", None)
    if not factory:
        raise RuntimeError("Backend factory not initialised")
    return _SandboxManager(factory)

