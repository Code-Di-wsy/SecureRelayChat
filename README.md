# Secure Relay Chat

Educational two-person command-line chat demonstrating the application-layer
chain `X25519 -> HKDF -> AES-256-GCM -> Ed25519`, with a six-digit safety number
for manual man-in-the-middle detection. The relay server only routes JSON and
never receives plaintext or private keys.

## Run

```text
python -m pip install -r requirements.txt
python main.py --server --port 8765
python main.py --client alice --server ws://127.0.0.1:8765
python main.py --client bob --server ws://127.0.0.1:8765
```

`--server-url` is also accepted for the client form.

In each client, use `/chat bob`, compare the displayed safety number out of
band, enter `/send hello`, and type `/quit` to clear the in-memory session.

This is a teaching demo, not a production messenger: it intentionally omits
forward secrecy, persistence, groups, offline delivery, and security auditing.
