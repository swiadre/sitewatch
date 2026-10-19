"""Append-only log of everything the remediator sees and does (JSON lines).

Used later by the chaos scripts to calculate MTTD / MTTR.
"""

import json
import threading
import time
from pathlib import Path


class EventLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def add(self, type: str, **fields) -> dict:
        event = {"ts": time.time(), "type": type, **fields}
        with self._lock, open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")
        print(f"[event] {event}", flush=True)
        return event

    def since(self, ts: float = 0) -> list[dict]:
        if not self.path.exists():
            return []
        events = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event["ts"] >= ts:
                    events.append(event)
        return events
