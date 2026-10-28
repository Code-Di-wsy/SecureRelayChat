"""Untrusted WebSocket relay: it only routes JSON frames by username."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed


USERS: dict[str, Any] = {}


async def _send(websocket: Any, frame: dict) -> None:
    await websocket.send(json.dumps(frame, separators=(",", ":")))


async def handle_client(websocket: Any, _path: str | None = None) -> None:
    username: str | None = None
    try:
        async for raw in websocket:
            try:
                frame = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                await _send(websocket, {"type": "error", "message": "invalid JSON"})
                continue
            if not isinstance(frame, dict):
                await _send(websocket, {"type": "error", "message": "frame must be an object"})
                continue
            frame_type = frame.get("type")
            if frame_type == "register":
                candidate = frame.get("username")
                if not isinstance(candidate, str) or not candidate:
                    await _send(websocket, {"type": "error", "message": "invalid username"})
                    await websocket.close()
                    return
                if username is not None:
                    await _send(websocket, {"type": "error", "message": "already registered"})
                    continue
                if candidate in USERS:
                    await _send(websocket, {"type": "error", "message": "username already online"})
                    await websocket.close()
                    return
                username = candidate
                USERS[username] = websocket
                await _send(websocket, {"type": "register_ok", "username": username})
            elif frame_type == "relay":
                if username is None:
                    await _send(websocket, {"type": "error", "message": "register first"})
                    continue
                target = frame.get("to")
                if not isinstance(target, str) or not target:
                    await _send(websocket, {"type": "error", "message": "invalid relay target"})
                    continue
                peer = USERS.get(target)
                if peer is None:
                    await _send(websocket, {"type": "error", "message": "peer offline"})
                    continue
                # Deliberately do not inspect or mutate payload contents.
                await _send(peer, {"type": "relay", "from": username, "payload": frame.get("payload")})
            else:
                await _send(websocket, {"type": "error", "message": "unknown frame type"})
    except ConnectionClosed:
        pass
    finally:
        if username is not None and USERS.get(username) is websocket:
            USERS.pop(username, None)


async def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    async with websockets.serve(handle_client, host, port):
        print(f"relay server listening on ws://{host}:{port}", flush=True)
        await asyncio.Future()


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    asyncio.run(run_server(host, port))


__all__ = ["USERS", "handle_client", "run_server", "serve"]
