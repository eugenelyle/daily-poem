"""Button server (page 2 on demand).

A tiny stdlib HTTP server for the Pi. An iPhone Shortcut (or any HTTP client on
the LAN) hits it to flip the panel between the poem and its companion:

  GET  /health     -> 200 {"status": "ok"}        connectivity check
  POST /companion  -> push the day's companion (page 2) to the Inky
  POST /poem       -> re-render today's poem (page 1) and push it

(GET is also accepted on the two actions so a Shortcut can be a single URL.)

Each action shells out to `python -m daily_poem ...` — a fresh process per press,
so the long-lived server never holds an Inky handle and a render crash can't take
it down. A lock serializes pushes: a second press while one is mid-refresh gets a
409 rather than colliding on the SPI bus (an e-ink refresh takes ~30s).

Local-network use only — there is no auth. Do not expose this port to the internet.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..config import Config

log = logging.getLogger(__name__)

_push_lock = threading.Lock()


def serve(cfg: Config, host: str | None = None, port: int | None = None) -> None:
    host = host if host is not None else cfg.companion.server_host
    port = port if port is not None else cfg.companion.server_port

    handler = _make_handler(cfg)
    httpd = ThreadingHTTPServer((host, port), handler)
    log.info("companion button server listening on %s:%d", host, port)
    print(f"companion button server on http://{host}:{port}  "
          f"(POST /companion, POST /poem, GET /health)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _make_handler(cfg: Config):
    repo_root = cfg.root

    class Handler(BaseHTTPRequestHandler):
        # Quieter logs: route through logging, not stderr prints.
        def log_message(self, fmt, *args):
            log.info("%s - %s", self.address_string(), fmt % args)

        def do_GET(self):
            if self.path.rstrip("/") in ("", "/health"):
                return self._json(200, {"status": "ok"})
            return self._dispatch_action()

        def do_POST(self):
            return self._dispatch_action()

        def _dispatch_action(self):
            path = self.path.rstrip("/")
            if path == "/companion":
                return self._run_action("companion", ["show-companion", "--target", "inky"])
            if path == "/poem":
                return self._run_action("poem", ["render", "--target", "inky"])
            return self._json(404, {"error": "not found", "path": self.path})

        def _run_action(self, label: str, argv: list[str]):
            if not _push_lock.acquire(blocking=False):
                return self._json(409, {"status": "busy",
                                        "detail": "a panel refresh is already in progress"})
            try:
                cmd = [sys.executable, "-m", "daily_poem", *argv]
                log.info("running %s: %s", label, " ".join(cmd))
                proc = subprocess.run(cmd, cwd=repo_root, capture_output=True,
                                      text=True, timeout=180)
                if proc.returncode == 0:
                    return self._json(200, {"status": "ok", "action": label,
                                            "output": proc.stdout.strip()})
                log.error("%s failed (rc=%d): %s", label, proc.returncode, proc.stderr.strip())
                return self._json(500, {"status": "error", "action": label,
                                        "detail": proc.stderr.strip()[-500:]})
            except subprocess.TimeoutExpired:
                return self._json(504, {"status": "timeout", "action": label})
            finally:
                _push_lock.release()

        def _json(self, code: int, body: dict):
            payload = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler
