"""Local-only storage for long-lived identity keys."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

import crypto
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization

_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_FIELDS = ("sign_priv", "ex_priv", "sign_pub", "ex_pub")


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object, field: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"invalid key field: {field}")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError(f"invalid base64 in key field: {field}") from exc


def _validate_username(username: str) -> None:
    if not isinstance(username, str) or not username or not _NAME.fullmatch(username):
        raise ValueError("username must contain only letters, digits, '.', '_' or '-'")


def load_or_create(username: str, base_dir: str = ".keys") -> dict[str, bytes]:
    _validate_username(username)
    directory = Path(base_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{username}.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != set(_FIELDS):
                raise ValueError("key file has invalid fields")
            result = {field: _decode(raw[field], field) for field in _FIELDS}
            if len(result["sign_priv"]) != 32 or len(result["ex_priv"]) != 32:
                raise ValueError("invalid private key length")
            if len(result["sign_pub"]) != 32 or len(result["ex_pub"]) != 32:
                raise ValueError("invalid public key length")
            # Detect files whose public values do not match their private values.
            if crypto.pub_bytes(Ed25519PrivateKey.from_private_bytes(result["sign_priv"])) != result["sign_pub"]:
                raise ValueError("signing public key does not match private key")
            if crypto.pub_bytes(X25519PrivateKey.from_private_bytes(result["ex_priv"])) != result["ex_pub"]:
                raise ValueError("exchange public key does not match private key")
            return result
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"cannot load key file {path}") from exc

    sign_priv, ex_priv = crypto.generate_identity_keys()
    result = {
        "sign_priv": sign_priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()),
        "ex_priv": ex_priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()),
        "sign_pub": crypto.pub_bytes(sign_priv),
        "ex_pub": crypto.pub_bytes(ex_priv),
    }
    encoded = {key: _b64(value) for key, value in result.items()}
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(encoded, handle, indent=2)
            handle.write("\n")
        os.chmod(path, 0o600)
    except FileExistsError:
        # Another process won the race; load its complete file.
        return load_or_create(username, base_dir)
    return result


def load_pub(username: str, base_dir: str = ".keys") -> tuple[bytes, bytes]:
    keys = load_or_create(username, base_dir)
    return keys["sign_pub"], keys["ex_pub"]


__all__ = ["load_or_create", "load_pub"]
