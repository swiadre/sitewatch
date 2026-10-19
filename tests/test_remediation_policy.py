from remediation.policy import RateLimiter, pick_action


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_pick_action():
    assert pick_action({"labels": {"remediation": "restart"}}) == "restart"
    assert pick_action({"labels": {"remediation": "rm -rf /"}}) is None
    assert pick_action({"labels": {}}) is None


def test_limit_per_hour():
    clock = FakeClock()
    rl = RateLimiter(max_actions=3, per_seconds=3600, cooldown_seconds=0, clock=clock)
    for i in range(3):
        assert rl.check("restart", f"site{i}").allowed
        rl.record("restart", f"site{i}")
        clock.t += 60

    verdict = rl.check("restart", "site9")
    assert not verdict.allowed
    assert "limit" in verdict.reason

    # an hour after the first action there's room again
    clock.t = 1000 + 3601
    assert rl.check("restart", "site9").allowed


def test_cooldown_per_target():
    clock = FakeClock()
    rl = RateLimiter(max_actions=10, cooldown_seconds=120, clock=clock)
    rl.record("restart", "demo")

    clock.t += 30
    assert not rl.check("restart", "demo").allowed
    # other action / other target is fine
    assert rl.check("rollback", "demo").allowed
    assert rl.check("restart", "other").allowed

    clock.t += 100
    assert rl.check("restart", "demo").allowed
