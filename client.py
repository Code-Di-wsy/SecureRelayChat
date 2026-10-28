"""CLI client for the educational secure relay chat."""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from typing import Callable, TextIO

import websockets
from websockets.exceptions import ConnectionClosed

import crypto
import key_store
from envelope import DecryptError, SignatureError, build_envelope, parse_envelope, verify_and_decrypt


class ChatClient:
    def __init__(self, username: str, server_url: str, key_dir: str = ".keys", *, output: TextIO | None = None):
        self.username = username
        self.server_url = server_url
        self.key_dir = key_dir
        self.output = output or sys.stdout
        raw = key_store.load_or_create(username, key_dir)
        self.sign_priv = raw["sign_priv"]
        self.ex_priv = raw["ex_priv"]
        self.sign_pub = raw["sign_pub"]
        self.ex_pub = raw["ex_pub"]
        self.websocket = None
        self.listener_task: asyncio.Task | None = None
        self.handshaked = False
        self.confirmed = False
        self.session_key: bytes | None = None
        self.temp_private = None
        self.temp_public: bytes | None = None
        self.peer: str | None = None
        self.peer_sign_pub: bytes | None = None
        self.peer_ex_pub: bytes | None = None
        self.safety_code: str | None = None

    def _print(self, message: str) -> None:
        print(message, file=self.output, flush=True)

    async def connect(self) -> None:
        self.websocket = await websockets.connect(self.server_url)
        await self.websocket.send(json.dumps({
            "type": "register", "username": self.username,
            "sign_pub": base64.b64encode(self.sign_pub).decode("ascii"),
            "ex_pub": base64.b64encode(self.ex_pub).decode("ascii"),
        }))
        response = json.loads(await self.websocket.recv())
        if response.get("type") != "register_ok":
            raise ConnectionError(response.get("message", "registration failed"))
        self.listener_task = asyncio.create_task(self._listen())
        self._print(f"logged in as {self.username}")

    async def _send_relay(self, to: str, payload: dict) -> None:
        if self.websocket is None:
            raise ConnectionError("not connected")
        await self.websocket.send(json.dumps({"type": "relay", "to": to, "payload": payload}, separators=(",", ":")))

    async def start_chat(self, peer: str) -> None:
        self._clear_session()
        self.peer = peer
        self.temp_private = crypto.generate_ephemeral_key()
        self.temp_public = crypto.pub_bytes(self.temp_private)
        await self._send_handshake(peer)

    async def _send_handshake(self, peer: str) -> None:
        assert self.temp_public is not None
        await self._send_relay(peer, {
            "type": "handshake", "from": self.username,
            "tmp_pub": base64.b64encode(self.temp_public).decode("ascii"),
            "sign_pub": base64.b64encode(self.sign_pub).decode("ascii"),
            "ex_pub": base64.b64encode(self.ex_pub).decode("ascii"),
        })

    async def _listen(self) -> None:
        assert self.websocket is not None
        try:
            async for raw in self.websocket:
                try:
                    frame = json.loads(raw)
                    if frame.get("type") == "relay":
                        await self._handle_payload(frame.get("payload"))
                    elif frame.get("type") == "error":
                        self._print(f"server error: {frame.get('message', 'unknown error')}")
                except Exception as exc:
                    self._print(f"invalid incoming frame: {exc}")
        except ConnectionClosed:
            self._print("disconnected")

    async def _handle_payload(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._print("invalid relay payload")
            return
        if payload.get("type") == "handshake":
            await self._handle_handshake(payload)
        elif payload.get("type") == "message":
            if not self.handshaked or self.session_key is None or self.peer_sign_pub is None:
                self._print("message received before handshake")
                return
            try:
                env = parse_envelope(payload)
                text = verify_and_decrypt(env, self.session_key, self.peer_sign_pub)
                self._print(f"{env.sender}: {text}")
            except (ValueError, SignatureError, DecryptError) as exc:
                self._print(f"message rejected: {exc}")

    async def _handle_handshake(self, payload: dict) -> None:
        try:
            peer = payload["from"]
            peer_tmp = base64.b64decode(payload["tmp_pub"], validate=True)
            peer_sign = base64.b64decode(payload["sign_pub"], validate=True)
            peer_ex = base64.b64decode(payload["ex_pub"], validate=True)
            if not isinstance(peer, str) or len(peer_tmp) != 32 or len(peer_sign) != 32 or len(peer_ex) != 32:
                raise ValueError("invalid handshake key length")
        except (KeyError, ValueError, TypeError, base64.binascii.Error) as exc:
            self._print(f"invalid handshake: {exc}")
            return
        if self.temp_private is None:
            self.peer = peer
            self.temp_private = crypto.generate_ephemeral_key()
            self.temp_public = crypto.pub_bytes(self.temp_private)
            await self._send_handshake(peer)
        self.peer = peer
        self.peer_sign_pub, self.peer_ex_pub = peer_sign, peer_ex
        assert self.temp_private is not None and self.temp_public is not None
        self.session_key = crypto.derive_session_key(self.temp_private, peer_tmp, self.temp_public)
        self.handshaked = True
        self.confirmed = False
        self.safety_code = crypto.safety_number(self.sign_pub, self.ex_pub, peer_sign, peer_ex)
        self._print(f"safety number for {peer}: {self.safety_code} (compare out of band; type y to confirm)")

    def confirm_safety(self, yes: bool) -> None:
        if not yes:
            self._clear_session()
            self._print("safety number not confirmed")
            return
        self.confirmed = bool(self.handshaked and self.session_key)
        self._print("secure session confirmed" if self.confirmed else "safety number not confirmed")

    async def send_message(self, text: str) -> bool:
        if not self.confirmed or self.session_key is None or not self.peer:
            self._print("secure session is not confirmed")
            return False
        payload = build_envelope(self.username, self.peer, self.session_key, text.encode("utf-8"),
                                 _ed_private(self.sign_priv))
        await self._send_relay(self.peer, payload)
        return True

    def _clear_session(self) -> None:
        self.session_key = None
        self.temp_private = None
        self.temp_public = None
        self.peer = None
        self.peer_sign_pub = None
        self.peer_ex_pub = None
        self.safety_code = None
        self.handshaked = False
        self.confirmed = False

    async def close(self) -> None:
        self._clear_session()
        if self.listener_task:
            self.listener_task.cancel()
        if self.websocket:
            await self.websocket.close()
        self.websocket = None

    async def command_loop(self, input_fn: Callable[[str], str] = input) -> None:
        while True:
            try:
                command = await asyncio.to_thread(input_fn, "> ")
            except (EOFError, KeyboardInterrupt):
                command = "/quit"
            if command == "/login" or command.startswith("/login "):
                if self.websocket is None:
                    await self.connect()
                else:
                    self._print("already logged in")
            elif command.startswith("/chat "):
                await self.start_chat(command[6:].strip())
            elif command.startswith("/send "):
                await self.send_message(command[6:])
            elif command.lower() in ("y", "n") and self.handshaked and not self.confirmed:
                self.confirm_safety(command.lower() == "y")
            elif command == "/safety":
                self._print(self.safety_code or "no active safety number")
            elif command in ("/quit", "/exit"):
                await self.close()
                return
            else:
                self._print("commands: /chat <user>, /send <message>, /safety, /quit")


def _ed_private(raw: bytes):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(raw)


async def run_client(username: str, server_url: str, key_dir: str = ".keys") -> None:
    client = ChatClient(username, server_url, key_dir)
    try:
        await client.connect()
        await client.command_loop()
    finally:
        await client.close()


__all__ = ["ChatClient", "run_client"]
