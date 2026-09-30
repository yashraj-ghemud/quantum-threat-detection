"""
server/api/ws.py
================
``/ws`` — the live event stream (backend plan section 13).

Client ops: ``subscribe`` / ``unsubscribe`` / ``ping``. The server greets with
``hello``, forwards hub events for the subscribed topics, reports ``lag`` when
the client's bounded queue overflowed, and sends a ``heartbeat`` every 15 s.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sentinel import __version__ as ENGINE_VERSION
from server.db.database import dumps
from server.services.hub import TOPICS

router = APIRouter()

MAX_CLIENTS = 32
HEARTBEAT_S = 15.0


def _envelope(type_: str, data, topic: str = "system") -> dict:
    return {"v": 1, "topic": topic, "type": type_, "ts": time.time(), "id": 0, "data": data}


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    ctx = ws.app.state.ctx
    hub = ctx.hub
    api_key = ctx.settings.api_key
    if api_key and ws.query_params.get("key") != api_key and ws.headers.get("x-api-key") != api_key:
        await ws.close(code=4401)
        return
    if hub.client_count >= MAX_CLIENTS:
        await ws.close(code=4429)
        return
    await ws.accept()
    sub = hub.subscribe()
    try:
        await ws.send_json(_envelope("hello", {
            "server_version": ENGINE_VERSION, "server_time": time.time(), "topics": list(TOPICS),
            "traffic": ctx.traffic.state(), "preset": ctx.engine.preset}))
        reader = asyncio.create_task(_reader(ws, sub))
        try:
            await _writer(ws, sub, reader)
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(sub)


async def _writer(ws: WebSocket, sub, reader: asyncio.Task) -> None:
    reported = 0
    while not reader.done():
        try:
            event = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_S)
        except asyncio.TimeoutError:
            await ws.send_json(_envelope("heartbeat", {"server_time": time.time()}))
            continue
        if sub.dropped > reported:
            await ws.send_json(_envelope("lag", {"dropped": sub.dropped - reported}))
            reported = sub.dropped
        await ws.send_text(dumps(event))


async def _reader(ws: WebSocket, sub) -> None:
    while True:
        raw = await ws.receive_text()
        try:
            msg = json.loads(raw)
        except ValueError:
            await ws.send_json(_envelope("error", {"message": "invalid JSON"}))
            continue
        op = msg.get("op") if isinstance(msg, dict) else None
        topics = {t for t in (msg.get("topics") or []) if t in TOPICS} if isinstance(msg, dict) else set()
        if op == "subscribe":
            sub.topics |= topics
            await ws.send_json(_envelope("subscribed", {"topics": sorted(sub.topics)}))
        elif op == "unsubscribe":
            sub.topics -= topics
            await ws.send_json(_envelope("subscribed", {"topics": sorted(sub.topics)}))
        elif op == "ping":
            await ws.send_json(_envelope("pong", {"t": msg.get("t"), "server_time": time.time()}))
        else:
            await ws.send_json(_envelope("error", {"message": f"unknown op {op!r}"}))
