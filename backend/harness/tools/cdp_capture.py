"""CDP Console and Network log capture for browser sessions.

Uses Chrome DevTools Protocol to subscribe to Console.messageAdded
and Network.* events, storing them as structured records.

Usage:
    capture = CDPCapture("ws://localhost:9222/devtools/browser/...")
    await capture.start()
    # ... browser actions ...
    logs = await capture.stop()
    console_logs = logs["console"]
    network_logs = logs["network"]
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class CDPCapture:
    """Subscribe to CDP Console + Network events for a browser session.

    Connects via the browser's WebSocket debug URL and registers event
    listeners for Console.messageAdded and selected Network events.
    Events are accumulated in-memory and returned as structured lists.
    """

    def __init__(self, cdp_url: str):
        self._cdp_url = cdp_url
        self._ws: Any = None
        self._console_logs: list[dict] = []
        self._network_logs: list[dict] = []
        self._running = False
        self._session_id: str | None = None

    async def start(self) -> None:
        """Connect to the CDP endpoint and subscribe to events."""
        if self._running:
            return
        try:
            import websockets
            self._ws = await websockets.connect(self._cdp_url, max_size=2**24, ping_interval=30)

            # Get the first available target and attach
            targets_resp = await self._send_command("Target.getTargets", {})
            targets = (targets_resp or {}).get("targetInfos", [])
            page_target = next(
                (t for t in targets if t.get("type") == "page"),
                None,
            )
            if not page_target:
                logger.warning("CDP: no page target found, attaching to first target")
                if not targets:
                    raise RuntimeError("CDP: no targets available")
                page_target = targets[0]

            attach_resp = await self._send_command(
                "Target.attachToTarget",
                {"targetId": page_target["targetId"], "flatten": True},
            )
            self._session_id = (attach_resp or {}).get("sessionId", "")

            # Subscribe to Console events
            await self._send_command("Console.enable", {}, session=True)
            # Subscribe to Network events
            await self._send_command("Network.enable", {}, session=True)

            self._running = True
            logger.info(
                "CDP capture started for %s (target=%s, session=%s)",
                self._cdp_url[:60],
                page_target.get("targetId", "")[:12],
                (self._session_id or "")[:12],
            )
        except Exception as e:
            logger.warning("CDP capture start failed: %s", e)
            self._running = False

    async def _send_command(self, method: str, params: dict, session: bool = False) -> dict | None:
        """Send a CDP command and wait for the response."""
        if not self._ws:
            return None
        cmd_id = id(method) + len(self._console_logs) + len(self._network_logs)
        msg: dict[str, Any] = {"id": cmd_id, "method": method, "params": params}
        if session and self._session_id:
            msg["sessionId"] = self._session_id
        try:
            await self._ws.send(json.dumps(msg))
            resp = await self._ws.recv()
            data = json.loads(resp)
            if "result" in data:
                return data["result"]
            if "method" in data:
                # It's an event, not a response
                self._handle_event(data)
                return None
            return data
        except Exception as e:
            logger.debug("CDP command %s failed: %s", method, e)
            return None

    async def _listen_loop(self) -> None:
        """Listen for CDP events until stopped."""
        try:
            while self._running and self._ws:
                try:
                    resp = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
                    data = json.loads(resp)
                    if "method" in data:
                        self._handle_event(data)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    if self._running:
                        logger.debug("CDP listen error: %s", e)
                    break
        except Exception:
            pass

    def _handle_event(self, data: dict) -> None:
        """Route a CDP event to the correct log accumulator."""
        method = data.get("method", "")
        params = data.get("params", {})

        if method == "Console.messageAdded":
            msg = params.get("message", {})
            self._console_logs.append({
                "level": msg.get("level", "log"),
                "text": msg.get("text", ""),
                "source": msg.get("source", ""),
                "url": msg.get("url", ""),
                "line": msg.get("line", 0),
                "timestamp": time.time(),
            })

        elif method == "Network.requestWillBeSent":
            req = params.get("request", {})
            self._network_logs.append({
                "type": "request",
                "requestId": params.get("requestId", ""),
                "url": req.get("url", ""),
                "method": req.get("method", ""),
                "headers": req.get("headers", {}),
                "timestamp": time.time(),
            })

        elif method == "Network.responseReceived":
            resp = params.get("response", {})
            req = params.get("request", {})
            self._network_logs.append({
                "type": "response",
                "requestId": params.get("requestId", ""),
                "url": resp.get("url", ""),
                "status": resp.get("status", 0),
                "statusText": resp.get("statusText", ""),
                "headers": resp.get("headers", {}),
                "mimeType": resp.get("mimeType", ""),
                "timestamp": time.time(),
            })

    async def stop(self) -> dict[str, list[dict]]:
        """Stop capture and return collected logs."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        result = {
            "console": self._console_logs,
            "network": self._network_logs,
        }
        self._console_logs = []
        self._network_logs = []
        logger.info("CDP capture stopped: %d console, %d network events", len(result["console"]), len(result["network"]))
        return result

    async def listen(self, duration: float = 5.0) -> dict[str, list[dict]]:
        """Capture events for a fixed duration, then return."""
        await self.start()
        await asyncio.sleep(duration)
        return await self.stop()


import asyncio
import time
