"""Everything that touches docker. Only the demo app container is managed here."""

import json
import os
import time
from pathlib import Path

import docker
from docker.errors import ImageNotFound, NotFound

CONTAINER = os.environ.get("DEMO_CONTAINER", "sitewatch-demo")
IMAGE = os.environ.get("DEMO_IMAGE", "sitewatch-demo")
NETWORK = os.environ.get("DEMO_NETWORK", "sitewatch_default")
SOURCE_DIR = os.environ.get("DEMO_SOURCE", "/demo")
DISK_SIZE = os.environ.get("DEMO_DISK_SIZE", "20m")
# also published on the host so the chaos scripts can measure recovery from outside
HOST_PORT = int(os.environ.get("DEMO_HOST_PORT", "8081"))


class DemoApp:
    def __init__(self, state_file: str | Path, client=None):
        self.client = client or docker.from_env()
        self.state_file = Path(state_file)

    # ---- deployment history ----

    def history(self) -> list[dict]:
        if not self.state_file.exists():
            return []
        return json.loads(self.state_file.read_text())

    def _save_history(self, history: list[dict]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(history, indent=2))

    def current_version(self) -> str | None:
        h = self.history()
        return h[-1]["version"] if h else None

    def last_deploy_time(self) -> float | None:
        h = self.history()
        return h[-1]["ts"] if h else None

    def previous_good_version(self) -> str | None:
        """Newest version before the current one that wasn't marked as bad."""
        h = self.history()
        current = self.current_version()
        for entry in reversed(h[:-1]):
            if entry["version"] != current and not entry.get("bad"):
                return entry["version"]
        return None

    # ---- actions ----

    def _ensure_image(self, version: str) -> str:
        tag = f"{IMAGE}:{version}"
        try:
            self.client.images.get(tag)
        except ImageNotFound:
            print(f"building {tag} ...", flush=True)
            self.client.images.build(path=SOURCE_DIR, tag=tag, buildargs={"APP_VERSION": version})
        return tag

    def deploy(self, version: str, reason: str = "manual") -> dict:
        tag = self._ensure_image(version)
        try:
            old = self.client.containers.get(CONTAINER)
            old.remove(force=True)
        except NotFound:
            pass

        self.client.containers.run(
            tag,
            name=CONTAINER,
            detach=True,
            network=NETWORK,
            # small tmpfs so the "disk full" chaos test fills it in a second
            tmpfs={"/data": f"size={DISK_SIZE}"},
            ports={"8080/tcp": HOST_PORT},
            labels={"sitewatch.managed": "true"},
        )
        entry = {"version": version, "ts": time.time(), "reason": reason}
        history = self.history()
        history.append(entry)
        self._save_history(history)
        return entry

    def rollback(self) -> dict:
        bad = self.current_version()
        target = self.previous_good_version()
        if target is None:
            raise RuntimeError("no previous good version to roll back to")
        history = self.history()
        history[-1]["bad"] = True
        self._save_history(history)
        entry = self.deploy(target, reason=f"rollback from {bad}")
        return {**entry, "from": bad}

    def restart(self) -> dict:
        c = self.client.containers.get(CONTAINER)
        status_before = c.status
        # kill + start instead of restart(): a hung app ignores SIGTERM anyway,
        # and waiting 10s for the graceful stop timeout would just make MTTR worse
        if c.status in ("running", "paused"):
            c.kill()
        c.start()
        return {"status_before": status_before}

    def cleanup_disk(self) -> dict:
        """Delete everything in /data/tmp (the temp/cache dir)."""
        c = self.client.containers.get(CONTAINER)
        result = c.exec_run(["sh", "-c", "du -sh /data/tmp 2>/dev/null; rm -rf /data/tmp/*"])
        return {"output": result.output.decode().strip()}

    def ensure_running(self, default_version: str = "1.0") -> None:
        """On remediator start: make sure the demo app exists."""
        try:
            self.client.containers.get(CONTAINER)
        except NotFound:
            version = self.current_version() or default_version
            self.deploy(version, reason="startup")
