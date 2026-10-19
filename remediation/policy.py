"""Decides IF we are allowed to fix something automatically.

Auto-remediation can make things worse (restart loop, rollback of a good version...),
so there are 2 safety limits:
- max N actions per hour in total, after that only a human gets alerted
- cooldown per action+target, so we don't restart the same thing every 30s
"""

import time
from collections import deque
from dataclasses import dataclass

KNOWN_ACTIONS = {"restart", "rollback", "cleanup_disk"}


def pick_action(alert: dict) -> str | None:
    """The alert rule says what to do in the `remediation` label."""
    action = alert.get("labels", {}).get("remediation")
    return action if action in KNOWN_ACTIONS else None


@dataclass
class Verdict:
    allowed: bool
    reason: str = ""


class RateLimiter:
    def __init__(
        self,
        max_actions: int = 3,
        per_seconds: float = 3600,
        cooldown_seconds: float = 120,
        clock=time.time,
    ):
        self.max_actions = max_actions
        self.per_seconds = per_seconds
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self.history: deque[float] = deque()
        self.last_by_key: dict[str, float] = {}

    def check(self, action: str, target: str) -> Verdict:
        now = self.clock()
        # forget actions older than the window
        while self.history and now - self.history[0] > self.per_seconds:
            self.history.popleft()

        if len(self.history) >= self.max_actions:
            return Verdict(
                False, f"limit of {self.max_actions} actions per {self.per_seconds:.0f}s reached"
            )

        last = self.last_by_key.get(f"{action}:{target}")
        if last is not None and now - last < self.cooldown_seconds:
            return Verdict(False, f"cooldown, last {action} was {now - last:.0f}s ago")

        return Verdict(True)

    def record(self, action: str, target: str) -> None:
        now = self.clock()
        self.history.append(now)
        self.last_by_key[f"{action}:{target}"] = now
