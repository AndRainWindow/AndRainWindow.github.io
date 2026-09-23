"""Loopback-only preview server, stopped by session removal or after one hour."""
import argparse
import functools
import http.server
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--token', required=True)
    parser.add_argument('--ready', required=True)
    args = parser.parse_args()
    session = Path(args.session)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=args.root)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    server.timeout = 1
    server.daemon_threads = True
    Path(args.ready).write_text(json.dumps({'port': server.server_port}), encoding='utf-8')
    deadline = time.monotonic() + 3600
    try:
        while time.monotonic() < deadline:
            try:
                if session.read_text() != args.token:
                    break
            except FileNotFoundError:
                break
            server.handle_request()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
