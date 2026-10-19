"""Failure scenarios for the demo app.

Every scenario knows:
- how to break the app (inject)
- which alert should catch it
- what a human would run to fix it (for runs without auto-remediation)
- how to clean up leftovers after a run
"""

import subprocess
from dataclasses import dataclass, field

import httpx

DEMO = "sitewatch-demo"
DEMO_URL = "http://localhost:8081"
REMEDIATOR = "http://localhost:9000"
NETSHOOT = "nicolaka/netshoot:v0.13"


def sh(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)


def tc(args: str, check: bool = True) -> subprocess.CompletedProcess:
    # run `tc` inside the demo container's network namespace using a helper container,
    # the demo image doesn't have iproute2 and shouldn't need NET_ADMIN
    return sh(
        f"docker run --rm --net container:{DEMO} --cap-add NET_ADMIN {NETSHOOT} tc {args}",
        check=check,
    )


@dataclass
class Scenario:
    name: str
    description: str
    alerts: list[str]
    manual_fix: str
    inject_cmd: str = ""
    cleanup_cmds: list[str] = field(default_factory=list)

    def inject(self) -> None:
        sh(self.inject_cmd)

    def cleanup(self) -> None:
        for cmd in self.cleanup_cmds:
            sh(cmd, check=False)


class Hang(Scenario):
    def inject(self) -> None:
        httpx.get(f"{DEMO_URL}/chaos/hang", timeout=5)


class Latency(Scenario):
    def inject(self) -> None:
        tc("qdisc add dev eth0 root netem delay 800ms")

    def cleanup(self) -> None:
        # after an auto restart the qdisc is already gone (new network namespace)
        tc("qdisc del dev eth0 root", check=False)


class BadDeploy(Scenario):
    def inject(self) -> None:
        httpx.post(f"{REMEDIATOR}/deploy", json={"version": "1.1-bad"}, timeout=120)


SCENARIOS = {
    s.name: s
    for s in [
        Scenario(
            name="kill",
            description="container killed (SIGKILL), like an OOM kill or a crash",
            alerts=["DemoUnresponsive"],
            inject_cmd=f"docker kill {DEMO}",
            manual_fix=f"docker start {DEMO}",
        ),
        Hang(
            name="hang",
            description="process alive but deadlocked, every request hangs",
            alerts=["DemoUnresponsive"],
            manual_fix=f"docker restart -t 0 {DEMO}",
        ),
        Latency(
            name="latency",
            description="+800 ms network delay on the container (tc netem)",
            alerts=["DemoSlow"],
            manual_fix=(
                f"docker run --rm --net container:{DEMO} --cap-add NET_ADMIN {NETSHOOT} "
                "tc qdisc del dev eth0 root"
            ),
        ),
        Scenario(
            name="disk",
            description="data disk filled up to 100% with junk in /data/tmp",
            alerts=["DemoDiskAlmostFull"],
            inject_cmd=(
                f"docker exec {DEMO} sh -c "
                "'dd if=/dev/zero of=/data/tmp/junk bs=1M count=100 2>/dev/null; true'"
            ),
            manual_fix=f"docker exec {DEMO} sh -c 'rm -rf /data/tmp/*'",
            cleanup_cmds=[f"docker exec {DEMO} sh -c 'rm -f /data/tmp/junk'"],
        ),
        BadDeploy(
            name="bad_deploy",
            description="deploy of a version that returns 500 on every request",
            alerts=["DemoErrorsAfterDeploy"],
            manual_fix=(
                f"curl -X POST {REMEDIATOR}/deploy -H 'Content-Type: application/json' "
                """-d '{"version": "1.0"}'"""
            ),
        ),
    ]
}
