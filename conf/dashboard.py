#!/usr/bin/env python3
"""Read-only monitoring for SimpleX control ports (localhost only)."""
import html
import os
import re
import select
import socket
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = int(os.environ.get("SIMPLEX_DASHBOARD_PORT", "5229"))
SMP = Path("/etc/opt/simplex/smp-server.ini")
XFTP = Path("/etc/opt/simplex-xftp/file-server.ini")

def setting(path, section, key):
    current = None
    for line in path.read_text().splitlines():
        match = re.match(r"^\s*\[([^]]+)\]", line)
        if match:
            current = match.group(1)
        if current == section:
            match = re.match(r"^\s*" + re.escape(key) + r"\s*[:=]\s*(.*?)\s*$", line)
            if match:
                return match.group(1)
    raise ValueError("Control setting not configured")

def receive(sock, idle=0.25):
    result = bytearray()
    deadline = time.monotonic() + 2
    while len(result) < 24000 and time.monotonic() < deadline:
        ready, _, _ = select.select([sock], [], [], idle)
        if not ready:
            break
        part = sock.recv(4096)
        if not part:
            break
        result.extend(part)
    return result.decode("utf-8", errors="replace")

def command(path, cmd):
    port = int(setting(path, "TRANSPORT", "control_port"))
    password = setting(path, "AUTH", "control_port_user_password")
    if not 1 <= port <= 65535 or not re.fullmatch(r"[A-Za-z0-9_-]+", password):
        raise ValueError("Control port credentials invalid")
    with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
        receive(sock)
        sock.sendall(("auth " + password + "\n").encode())
        auth = receive(sock)
        if any(s in auth.lower() for s in ("failed", "invalid", "unauthorized", "error")):
            raise RuntimeError("Control authentication failed")
        sock.sendall((cmd + "\n").encode())
        response = receive(sock)
    return response.strip() or "(no response)"

def latest_xftp_stats():
    path = Path("/var/opt/simplex-xftp/file-server-stats.daily.log")
    if not path.exists():
        return "No XFTP daily statistics file yet."
    with path.open("rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 8192))
        lines = f.read().decode(errors="replace").splitlines()
    return lines[-1] if lines else "No statistics recorded."

def render():
    sections = []
    for title, path, commands in (
        ("SMP messaging", SMP, ("stats", "server-info", "sockets")),
        ("XFTP file transfers", XFTP, ("help",)),
    ):
        rows = []
        for cmd in commands:
            try:
                output = command(path, cmd)
            except Exception as exc:
                output = "Unavailable: " + str(exc)
            rows.append('<details ' + ("open" if cmd == commands[0] else "") + '><summary>' +
                        html.escape(cmd) + '</summary><pre>' + html.escape(output) + '</pre></details>')
        sections.append("<section><h2>" + html.escape(title) + "</h2>" + "".join(rows) + "</section>")
    sections.append("<section><h2>XFTP daily statistics</h2><pre>" + html.escape(latest_xftp_stats()) + "</pre></section>")
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SimpleX monitoring</title><style>body{font:16px system-ui,sans-serif;background:#f5f7fa;color:#17283e;max-width:1100px;margin:2rem auto;padding:0 1rem}
section{background:white;padding:1.2rem;border:1px solid #dce3ed;border-radius:12px;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f3f7;padding:1rem}
summary{padding:.6rem;cursor:pointer;font-weight:bold}h1{color:#1265bb}</style></head><body><h1>SimpleX monitoring</h1>
<p>Read-only status from localhost control ports. Refresh for current data.</p><small>Updated ''' +
            html.escape(updated) + "</small>" + "".join(sections) + "</body></html>")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return
        data = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
