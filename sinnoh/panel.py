"""Serve the Pokétch panel for T3 Desktop's docked browser on this machine."""
from argparse import ArgumentTypeError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import socket
import sys
from threading import Thread
from time import sleep

from .paths import ASSETS
from .usage import read_providers

HOST = "127.0.0.1"
DEFAULT_PORT = 47984
PANEL_PATH = "/poketch/"
FILES = {
    PANEL_PATH: ("index.html", "text/html"),
    PANEL_PATH + "panel.css": ("panel.css", "text/css"),
    PANEL_PATH + "panel.mjs": ("panel.mjs", "text/javascript"),
    PANEL_PATH + "model.mjs": ("model.mjs", "text/javascript"),
}
USAGE_PATH = PANEL_PATH + "usage.json"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def panel_url(port):
    return f"http://{HOST}:{port}{PANEL_PATH}"


def parse_port(value):
    try:
        port = int(value)
        if 1024 <= port <= 65535:
            return port
    except ValueError:
        pass
    raise ArgumentTypeError("expected a port from 1024 to 65535")


def quota_snapshot(root):
    # Project the public quota fields explicitly. Never return raw provider/cache records.
    return [{
        "id": provider.id,
        "name": provider.name,
        "status": provider.status,
        "checked": provider.checked.isoformat() if provider.checked else None,
        "windows": [{
            "id": window.id,
            "label": window.label,
            "used": window.used,
            "reset": window.reset.isoformat() if window.reset else None,
        } for window in provider.windows],
    } for provider in read_providers(root)]


class PanelRequest(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def do_GET(self):
        port = self.server.server_port
        if self.headers.get_all("Host") not in ([f"{HOST}:{port}"], [f"localhost:{port}"]):
            self.send_error(400)
            return
        if self.path == USAGE_PATH:
            # A cross-origin site cannot supply the custom header without a successful
            # CORS preflight. Reject cross-site fetches and do not enable CORS.
            if (self.headers.get("X-Sinnoh-Panel") != "1"
                    or self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin"):
                self.send_error(403)
                return
            data = json.dumps(quota_snapshot(self.server.root), allow_nan=False).encode()
            mime = "application/json"
        elif self.path in FILES:
            file, mime = FILES[self.path]
            data = (ASSETS / "poketch" / file).read_bytes()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Sinnoh-Lake", "poketch")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


class PanelServer(ThreadingHTTPServer):
    def __init__(self, root, port):
        self.root = root
        super().__init__((HOST, port), PanelRequest)

    def server_bind(self):
        if sys.platform == "win32":
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def clock(root, port):
    from .solar import sync

    while True:
        try:
            sync(root, poketch_url=panel_url(port))
        except Exception:
            logging.exception("Could not update the lake theme. Retrying in one minute.")
        sleep(60)


def serve(root, port):
    with PanelServer(root, port) as server:
        logging.info("Pokétch ready at %s", panel_url(port))
        Thread(target=clock, args=(root, port), daemon=True).start()
        server.serve_forever()
