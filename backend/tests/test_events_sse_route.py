"""Tests for the ``/api/events/{session_id}`` SSE route.

End-to-end streaming via ``httpx.AsyncClient`` + ``ASGITransport``
unwinds unreliably under ``pytest-asyncio`` strict mode on Windows
(the Proactor loop holds onto the receive channel).  Similarly,
``fastapi.testclient.TestClient`` runs the ASGI app in a portal that
doesn't shut down cleanly inside a strict-mode event loop.  So we
test the route without a transport:

  1. **Route table** — sync introspection.  No event loop, no transport.
  2. **Direct endpoint call** — call the endpoint coroutine ourselves,
     iterate its ``EventSourceResponse.body_iterator`` with a hard
     ``wait_for`` deadline, and assert on the frames.  No HTTP transport.
  3. **503 path** — call the endpoint without a sink attached and
     assert the HTTPException propagates with status 503.

The 30-line route is mostly glue (subscribe → loop on queue → yield
→ unsubscribe); the load-bearing logic lives in ``EventSourceSink``
which has its own dedicated test file.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.exceptions import HTTPException

from api.routers.events import KEEPALIVE_INTERVAL_SECONDS, router as events_router
from harness.events import EventSourceSink
from harness.core.events import StreamEvent
from harness.api.state import GenericStreamEvent


pytestmark = pytest.mark.asyncio


_FRAME_DEADLINE_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_app(with_sink: bool) -> FastAPI:
    app = FastAPI()
    if with_sink:
        app.state.event_source_sink = EventSourceSink()
    app.include_router(events_router)
    return app


def _find_route(app: FastAPI, path: str):
    for r in app.router.routes:
        if getattr(r, "path", "") == path:
            return r
    raise KeyError(path)


def _build_fake_request(app: FastAPI, *, send_disconnect_on_first_receive: bool = False):
    """Build a Starlette Request with a controllable receive channel.

    If ``send_disconnect_on_first_receive`` is True, the first call to
    ``receive()`` returns an ``http.disconnect`` event (mimicking a
    client that hung up immediately).  Otherwise the receive channel
    blocks forever — the test must ``aclose()`` the body iterator to
    stop the route's generator.
    """
    from starlette.requests import Request

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/events/sess-test",
        "raw_path": b"/api/events/sess-test",
        "query_string": b"",
        "headers": [(b"host", b"test")],
        "client": ("test", 12345),
        "server": ("test", 80),
        "app": app,
    }
    sent = {"disconnect": False}
    disconnect_event = {"type": "http.disconnect"}

    async def receive():
        if send_disconnect_on_first_receive and not sent["disconnect"]:
            sent["disconnect"] = True
            return disconnect_event
        # Block forever — tests must aclose() the body iterator.
        await asyncio.Event().wait()

    async def send(_message):
        pass

    return Request(scope, receive=receive, send=send)


# ---------------------------------------------------------------------------
# Route registration (sync, no event loop)
# ---------------------------------------------------------------------------


def test_routes_are_registered() -> None:
    paths = sorted({r.path for r in events_router.routes})
    assert "/api/events/{session_id}" in paths
    assert "/api/events/_stats" in paths


def test_keepalive_interval_is_sane() -> None:
    """Keepalive must be < the typical LB idle timeout (60s) but not chatty."""
    assert 5.0 <= KEEPALIVE_INTERVAL_SECONDS <= 55.0


# ---------------------------------------------------------------------------
# 503 path — endpoint raises HTTPException when sink missing
# ---------------------------------------------------------------------------


async def test_stream_endpoint_raises_503_when_sink_missing() -> None:
    app = _build_app(with_sink=False)
    route = _find_route(app, "/api/events/{session_id}")
    request = _build_fake_request(app)
    with pytest.raises(HTTPException) as exc_info:
        await route.endpoint(request, session_id="anything")
    assert exc_info.value.status_code == 503
    assert "event_source_sink" in exc_info.value.detail


async def test_stats_endpoint_raises_503_when_sink_missing() -> None:
    app = _build_app(with_sink=False)
    route = _find_route(app, "/api/events/_stats")
    request = _build_fake_request(app)
    with pytest.raises(HTTPException) as exc_info:
        await route.endpoint(request)
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# /api/events/_stats — call the endpoint directly (no HTTP transport)
# ---------------------------------------------------------------------------


async def test_stats_endpoint_reports_no_subscribers() -> None:
    app = _build_app(with_sink=True)
    route = _find_route(app, "/api/events/_stats")
    request = _build_fake_request(app)
    result = await route.endpoint(request)
    assert result == {"sessions": [], "session_count": 0, "total_subscribers": 0}


async def test_stats_endpoint_reports_subscribers() -> None:
    app = _build_app(with_sink=True)
    sink: EventSourceSink = app.state.event_source_sink
    sink.subscribe("sess-a")
    sink.subscribe("sess-a")
    sink.subscribe("sess-b")
    route = _find_route(app, "/api/events/_stats")
    request = _build_fake_request(app)
    result = await route.endpoint(request)
    assert result == {
        "sessions": ["sess-a", "sess-b"],
        "session_count": 2,
        "total_subscribers": 3,
    }


# ---------------------------------------------------------------------------
# Direct endpoint call (no HTTP transport) — exercise the streaming body
# ---------------------------------------------------------------------------


async def test_endpoint_yields_connected_frame_on_subscribe() -> None:
    app = _build_app(with_sink=True)
    sink: EventSourceSink = app.state.event_source_sink
    route = _find_route(app, "/api/events/{session_id}")
    request = _build_fake_request(app)

    response = await route.endpoint(request, session_id="sess-test")
    body_iter = response.body_iterator
    chunks: list[dict] = []
    try:
        first = await asyncio.wait_for(body_iter.__anext__(), timeout=_FRAME_DEADLINE_SECONDS)
        chunks.append(first)
    except (asyncio.TimeoutError, StopAsyncIteration):
        pass
    await body_iter.aclose()

    assert len(chunks) == 1
    assert chunks[0]["event"] == "connected"
    assert json.loads(chunks[0]["data"]) == {"session_id": "sess-test"}
    # The route's finally-block unsubscribed before returning.
    assert sink.subscriber_count("sess-test") == 0


async def test_endpoint_streams_events_from_sink() -> None:
    app = _build_app(with_sink=True)
    sink: EventSourceSink = app.state.event_source_sink
    route = _find_route(app, "/api/events/{session_id}")
    request = _build_fake_request(app)

    response = await route.endpoint(request, session_id="sess-test")
    body_iter = response.body_iterator

    # Kick the generator once so the route's ``subscribe()`` runs.
    connected = await asyncio.wait_for(body_iter.__anext__(), timeout=_FRAME_DEADLINE_SECONDS)
    assert connected["event"] == "connected"
    assert sink.subscriber_count("sess-test") == 1

    sink.emit(GenericStreamEvent(session_id="sess-test", event_type="agent:start", data={"hello": "world"}))
    sink.emit(GenericStreamEvent(session_id="sess-test", event_type="tool:end", data={"ok": True}))

    e1 = await asyncio.wait_for(body_iter.__anext__(), timeout=_FRAME_DEADLINE_SECONDS)
    e2 = await asyncio.wait_for(body_iter.__anext__(), timeout=_FRAME_DEADLINE_SECONDS)

    assert e1["event"] == "agent:start"
    assert json.loads(e1["data"])["data"] == {"hello": "world"}
    assert e2["event"] == "tool:end"
    assert json.loads(e2["data"])["data"] == {"ok": True}
    assert json.loads(e1["data"])["session_id"] == "sess-test"
    assert json.loads(e2["data"])["session_id"] == "sess-test"

    # Stop the generator explicitly — no need to wait for the route's
    # disconnect-detection poll (which is hard to test deterministically
    # under pytest-asyncio strict mode).
    await body_iter.aclose()


async def test_endpoint_does_not_cross_session_boundaries() -> None:
    app = _build_app(with_sink=True)
    sink: EventSourceSink = app.state.event_source_sink
    route = _find_route(app, "/api/events/{session_id}")
    request = _build_fake_request(app)

    response = await route.endpoint(request, session_id="sess-test")
    body_iter = response.body_iterator

    connected = await asyncio.wait_for(body_iter.__anext__(), timeout=_FRAME_DEADLINE_SECONDS)
    assert connected["event"] == "connected"

    sink.emit(GenericStreamEvent(session_id="sess-OTHER", event_type="wrong", data={}))
    sink.emit(GenericStreamEvent(session_id="sess-test", event_type="right", data={}))

    right = await asyncio.wait_for(body_iter.__anext__(), timeout=_FRAME_DEADLINE_SECONDS)
    assert right["event"] == "right"
    # Confirm the wrong event didn't sneak in.
    assert sink.subscriber_count("sess-OTHER") == 0
    await body_iter.aclose()
