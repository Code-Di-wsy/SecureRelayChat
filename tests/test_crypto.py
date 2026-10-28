import pytest

import crypto


def test_ephemeral_derivation_is_symmetric_and_session_bound():
    alice = crypto.generate_ephemeral_key()
    bob = crypto.generate_ephemeral_key()
    alice_pub = crypto.pub_bytes(alice)
    bob_pub = crypto.pub_bytes(bob)
    left = crypto.derive_session_key(alice, bob_pub, alice_pub)
    right = crypto.derive_session_key(bob, alice_pub, bob_pub)
    assert left == right
    other = crypto.generate_ephemeral_key()
    assert left != crypto.derive_session_key(other, bob_pub, crypto.pub_bytes(other))


def test_aes_gcm_round_trip_and_authentication():
    key = b"k" * 32
    nonce, ciphertext = crypto.encrypt(key, b"hello", b"alice:bob")
    assert len(nonce) == 12
    assert crypto.decrypt(key, nonce, ciphertext, b"alice:bob") == b"hello"
    with pytest.raises(Exception):
        crypto.decrypt(key, nonce, ciphertext, b"alice:eve")


def test_safety_number_is_symmetric_and_six_digits():
    a = (b"a" * 32, b"b" * 32)
    b = (b"c" * 32, b"d" * 32)
    left = crypto.safety_number(*a, *b)
    right = crypto.safety_number(*b, *a)
    assert left == right
    assert len(left) == 6 and left.isdecimal()
