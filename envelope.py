"""Authenticated, encrypted message envelopes."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

import crypto


class SignatureError(ValueError):
    pass


class DecryptError(ValueError):
    pass


@dataclass(frozen=True)
class MessageEnvelope:
    sender: str
    recipient: str
    nonce: bytes
    ciphertext: bytes
    signature: bytes


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object, field: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be base64 text")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError(f"invalid base64 in {field}") from exc


def build_envelope(sender: str, recipient: str, session_key: bytes, plaintext: bytes, identity_sign_priv) -> dict:
    if not isinstance(sender, str) or not isinstance(recipient, str) or not sender or not recipient:
        raise ValueError("sender and recipient are required")
    aad = f"{sender}:{recipient}".encode("utf-8")
    nonce, ciphertext = crypto.encrypt(session_key, plaintext, aad)
    digest = hashlib.sha256(nonce + ciphertext + aad).digest()
    signature = crypto.sign(identity_sign_priv, digest)
    return {
        "type": "message", "sender": sender, "recipient": recipient,
        "nonce": _encode(nonce), "ciphertext": _encode(ciphertext),
        "signature": _encode(signature),
    }


def parse_envelope(frame: dict) -> MessageEnvelope:
    if not isinstance(frame, dict) or frame.get("type") != "message":
        raise ValueError("not a message envelope")
    for field in ("sender", "recipient", "nonce", "ciphertext", "signature"):
        if field not in frame:
            raise ValueError(f"missing envelope field: {field}")
    sender, recipient = frame["sender"], frame["recipient"]
    if not isinstance(sender, str) or not isinstance(recipient, str) or not sender or not recipient:
        raise ValueError("invalid sender or recipient")
    nonce = _decode(frame["nonce"], "nonce")
    ciphertext = _decode(frame["ciphertext"], "ciphertext")
    signature = _decode(frame["signature"], "signature")
    if len(nonce) != 12:
        raise ValueError("nonce must be 12 bytes")
    if len(signature) != 64:
        raise ValueError("signature must be 64 bytes")
    if len(ciphertext) < 16:
        raise ValueError("ciphertext is missing its GCM tag")
    return MessageEnvelope(sender, recipient, nonce, ciphertext, signature)


def verify_and_decrypt(env: MessageEnvelope, session_key: bytes, peer_sign_pub: bytes) -> str:
    aad = f"{env.sender}:{env.recipient}".encode("utf-8")
    digest = hashlib.sha256(env.nonce + env.ciphertext + aad).digest()
    if not crypto.verify(peer_sign_pub, digest, env.signature):
        raise SignatureError("message signature verification failed")
    try:
        plaintext = crypto.decrypt(session_key, env.nonce, env.ciphertext, aad)
    except Exception as exc:
        raise DecryptError("message decryption failed") from exc
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecryptError("message is not valid UTF-8") from exc


__all__ = ["MessageEnvelope", "SignatureError", "DecryptError", "build_envelope", "parse_envelope", "verify_and_decrypt"]
