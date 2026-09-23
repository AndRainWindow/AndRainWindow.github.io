"""Loopback-only preview server, stopped by session removal or after one hour."""
import argparse
import functools
import http.server
import json
import time
import os
import socketserver
from pathlib import Path


class PreviewServer(http.server.ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer normally performs a reverse DNS lookup even for loopback;
        # avoid slow/offline DNS on macOS and Windows during local startup.
        socketserver.TCPServer.server_bind(self)
        self.server_name = 'localhost'
        self.server_port = self.server_address[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--token', required=True)
    parser.add_argument('--ready', required=True)
    args = parser.parse_args()
    session = Path(args.session)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=args.root)
    server = PreviewServer(('127.0.0.1', 0), handler)
    server.timeout = 1
    server.daemon_threads = True
    ready = Path(args.ready)
    temporary = ready.with_suffix('.tmp')
    temporary.write_text(json.dumps({'port': server.server_port}), encoding='utf-8')
    os.replace(temporary, ready)
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
