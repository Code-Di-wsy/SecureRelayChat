"""Small, auditable wrappers around the cryptography primitives used by the demo."""

from __future__ import annotations

import hashlib
import os
from typing import Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

Key = Union[Ed25519PrivateKey, X25519PrivateKey]


def generate_identity_keys() -> tuple[Ed25519PrivateKey, X25519PrivateKey]:
    return Ed25519PrivateKey.generate(), X25519PrivateKey.generate()


def generate_ephemeral_key() -> X25519PrivateKey:
    return X25519PrivateKey.generate()


def pub_bytes(private_key: Key) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def sign(private_key: Ed25519PrivateKey, data: bytes) -> bytes:
    return private_key.sign(data)


def verify(public_key_bytes: bytes, data: bytes, signature: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, data)
        return True
    except Exception:
        # Invalid signatures and malformed public keys are both a normal false result.
        return False


def derive_session_key(
    my_ephemeral_priv: X25519PrivateKey,
    peer_ephemeral_pub: bytes,
    my_ephemeral_pub: bytes,
    peer_ephemeral_pub_compat: bytes | None = None,
) -> bytes:
    """Derive a session key from ephemeral X25519 keys.

    The fourth argument is accepted for compatibility with early drafts of the
    exercise which accidentally listed the peer public key twice.  It is not
    needed: ``peer_ephemeral_pub`` already supplies that value.
    """
    del peer_ephemeral_pub_compat
    if len(peer_ephemeral_pub) != 32 or len(my_ephemeral_pub) != 32:
        raise ValueError("X25519 public keys must be 32 bytes")
    shared = my_ephemeral_priv.exchange(X25519PublicKey.from_public_bytes(peer_ephemeral_pub))
    salt = b"".join(sorted((my_ephemeral_pub, peer_ephemeral_pub)))
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=salt,
        info=b"SecureRelayChat v2 session key",
    ).derive(shared)


def encrypt(session_key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    if len(session_key) != 32:
        raise ValueError("AES-256 session keys must be 32 bytes")
    nonce = os.urandom(12)
    return nonce, AESGCM(session_key).encrypt(nonce, plaintext, aad)


def decrypt(session_key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    if len(session_key) != 32:
        raise ValueError("AES-256 session keys must be 32 bytes")
    if len(nonce) != 12:
        raise ValueError("AES-GCM nonces must be 12 bytes")
    return AESGCM(session_key).decrypt(nonce, ciphertext, aad)


def safety_number(
    my_sign_pub: bytes,
    my_ex_pub: bytes,
    peer_sign_pub: bytes,
    peer_ex_pub: bytes,
) -> str:
    identities = sorted((my_sign_pub + my_ex_pub, peer_sign_pub + peer_ex_pub))
    digest = hashlib.sha256(b"".join(identities)).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


__all__ = [
    "InvalidTag", "generate_identity_keys", "generate_ephemeral_key", "pub_bytes",
    "sign", "verify", "derive_session_key", "encrypt", "decrypt", "safety_number",
]
