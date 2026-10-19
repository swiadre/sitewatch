"""Tiny web app used as a target for auto-remediation and chaos tests.

I don't want to break my real production sites on purpose, so this one gets broken instead.
Only stdlib, no dependencies.

- APP_VERSION env var is shown on the page
- a version with "bad" in the name returns 500 on every request (simulates a broken deploy)
- every request writes a temp file to DATA_DIR/tmp (like an upload/session cache would),
  so when the disk is full, requests fail
- GET /chaos/hang takes a lock and never gives it back -> every next request hangs forever
  (the process is alive, docker thinks it's fine, but nobody gets an answer = like a deadlock)
"""

import os
import shutil
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ.get("APP_VERSION", "dev")
DATA_DIR = os.environ.get("DATA_DIR", "/tmp/demo-data")
PORT = int(os.environ.get("PORT", "8080"))

# every request needs this lock for a moment, like a shared db connection would
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            return self.metrics()

        if self.path == "/chaos/hang":
            lock.acquire()  # never released
            return self.reply(200, "ok, hanging now\n")

        with lock:
            pass

        if "bad" in VERSION:
            return self.reply(500, f"version {VERSION} is broken :(\n")

        try:
            # a new file needs a new block on disk, so this fails when the disk is full
            # (appending one line to an existing file often still fits in the last block)
            with tempfile.NamedTemporaryFile(dir=os.path.join(DATA_DIR, "tmp"), delete=True) as f:
                f.write(f"{datetime.now().isoformat()} {self.path}\n".encode() * 64)
                f.flush()
        except OSError as e:
            # e.g. "No space left on device"
            return self.reply(500, f"can't write to disk: {e}\n")

        self.reply(200, f"<h1>sitewatch demo app</h1><p>version {VERSION}</p>\n")

    def metrics(self):
        usage = shutil.disk_usage(DATA_DIR)
        body = (
            "# TYPE demo_disk_free_bytes gauge\n"
            f"demo_disk_free_bytes {usage.free}\n"
            "# TYPE demo_disk_total_bytes gauge\n"
            f"demo_disk_total_bytes {usage.total}\n"
            "# TYPE demo_app_info gauge\n"
            f'demo_app_info{{version="{VERSION}"}} 1\n'
        )
        self.reply(200, body, "text/plain; version=0.0.4")

    def reply(self, code: int, body: str, content_type: str = "text/html") -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # too noisy, prober hits this every 10s


if __name__ == "__main__":
    os.makedirs(os.path.join(DATA_DIR, "tmp"), exist_ok=True)
    print(f"demo app {VERSION} listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
