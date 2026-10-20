"""Failure scenarios for the demo app.

Every scenario knows:
- how to break the app (inject)
- which alert should catch it
- what a human would run to fix it (for runs without auto-remediation)
- how to clean up leftovers after a run
"""

import os
import subprocess
from dataclasses import dataclass, field

import httpx

# docker = the docker compose setup in deploy/, k8s = the kind cluster from k8s/up.sh
TARGET = os.environ.get("CHAOS_TARGET", "docker")
DEMO = "sitewatch-demo"
NETSHOOT = "nicolaka/netshoot:v0.13"
if TARGET == "k8s":
    DEMO_URL, REMEDIATOR = "http://localhost:8082", "http://localhost:9002"
else:
    DEMO_URL, REMEDIATOR = "http://localhost:8081", "http://localhost:9000"
KUBECTL = "kubectl -n sitewatch"


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


def demo_pod() -> str:
    return sh(f"{KUBECTL} get pod -l app={DEMO} -o name").stdout.split()[0]


def k8s_tc(args: str, check: bool = True) -> subprocess.CompletedProcess:
    # ephemeral debug container in the demo pod: shares its network namespace, has NET_ADMIN
    return sh(
        f"{KUBECTL} debug {demo_pod()} --image={NETSHOOT} --profile=netadmin --attach=false "
        f"-- tc {args}",
        check=check,
    )


class K8sLatency(Scenario):
    def inject(self) -> None:
        k8s_tc("qdisc add dev eth0 root netem delay 800ms")

    def cleanup(self) -> None:
        k8s_tc("qdisc del dev eth0 root", check=False)


class BadDeploy(Scenario):
    def inject(self) -> None:
        httpx.post(f"{REMEDIATOR}/deploy", json={"version": "1.1-bad"}, timeout=120)


DOCKER_SCENARIOS = {
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


K8S_SCENARIOS = {
    s.name: s
    for s in [
        Scenario(
            name="kill",
            description="pod deleted (like a node problem or an OOM kill)",
            alerts=["DemoUnresponsive"],
            inject_cmd=f"{KUBECTL} delete pod -l app={DEMO} --grace-period=0 --force --wait=false",
            manual_fix="nothing, the ReplicaSet creates a new pod",
        ),
        Hang(
            name="hang",
            description="process alive but deadlocked, every request hangs",
            alerts=["DemoUnresponsive"],
            manual_fix=f"{KUBECTL} delete pod -l app={DEMO}",
        ),
        K8sLatency(
            name="latency",
            description="+800 ms network delay on the pod (tc netem in a debug container)",
            alerts=["DemoSlow"],
            manual_fix=f"{KUBECTL} delete pod -l app={DEMO}",
        ),
        Scenario(
            name="disk",
            description="data volume (20Mi tmpfs) filled up to 100%",
            alerts=["DemoDiskAlmostFull"],
            inject_cmd=(
                f"{KUBECTL} exec deploy/{DEMO} -- sh -c "
                "'dd if=/dev/zero of=/data/tmp/junk bs=1M count=100 2>/dev/null; true'"
            ),
            manual_fix=f"{KUBECTL} exec deploy/{DEMO} -- rm -rf /data/tmp/junk",
        ),
        BadDeploy(
            name="bad_deploy",
            description="deploy of a version that returns 500 on every request",
            alerts=["DemoErrorsAfterDeploy"],
            manual_fix=f'curl -X POST {REMEDIATOR}/deploy -d \'{{"version": "1.0"}}\'',
        ),
    ]
}

SCENARIOS = K8S_SCENARIOS if TARGET == "k8s" else DOCKER_SCENARIOS
