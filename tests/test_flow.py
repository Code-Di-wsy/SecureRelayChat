import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import crypto
import key_store
from envelope import DecryptError, SignatureError, build_envelope, parse_envelope, verify_and_decrypt


def test_envelope_round_trip_and_tamper_rejection():
    with tempfile.TemporaryDirectory() as directory:
        alice = key_store.load_or_create("alice", directory)
        bob = key_store.load_or_create("bob", directory)
        a_tmp = crypto.generate_ephemeral_key()
        b_tmp = crypto.generate_ephemeral_key()
        a_pub, b_pub = crypto.pub_bytes(a_tmp), crypto.pub_bytes(b_tmp)
        key_a = crypto.derive_session_key(a_tmp, b_pub, a_pub)
        key_b = crypto.derive_session_key(b_tmp, a_pub, b_pub)
        envelope = build_envelope(
            "alice", "bob", key_a, "hello".encode(),
            Ed25519PrivateKey.from_private_bytes(alice["sign_priv"]),
        )
        parsed = parse_envelope(envelope)
        assert verify_and_decrypt(parsed, key_b, alice["sign_pub"]) == "hello"

        envelope["ciphertext"] = envelope["ciphertext"][:-2] + "AA"
        tampered = parse_envelope(envelope)
        try:
            verify_and_decrypt(tampered, key_b, alice["sign_pub"])
        except (SignatureError, DecryptError):
            pass
        else:
            raise AssertionError("tampered message was accepted")
