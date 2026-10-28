from __future__ import annotations

import argparse
import asyncio

from client import run_client
from server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Educational two-person end-to-end encrypted chat")
    # ``--server`` is a flag in server mode and may also carry the relay URL
    # in the client form documented by the original exercise.
    parser.add_argument("--server", nargs="?", const=True, default=None,
                        help="run relay, or relay URL when used with --client")
    parser.add_argument("--client", metavar="USERNAME", help="run a chat client")
    parser.add_argument("--server-url", default="ws://127.0.0.1:8765", help="relay URL for --client")
    parser.add_argument("--port", type=int, default=8765, help="listen port for --server")
    parser.add_argument("--host", default="127.0.0.1", help="listen host for --server")
    parser.add_argument("--key-dir", default=".keys", help="directory for local identity keys")
    args = parser.parse_args()
    if args.server is True:
        asyncio.run(run_server(args.host, args.port))
    elif args.client:
        server_url = args.server if isinstance(args.server, str) else args.server_url
        asyncio.run(run_client(args.client, server_url, args.key_dir))
    else:
        parser.error("choose --server or --client USERNAME")


if __name__ == "__main__":
    main()
