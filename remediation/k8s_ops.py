"""Same actions as docker_ops.DemoApp, but for the demo app running in Kubernetes.

Permissions (k8s/remediator.yaml) are only: get/list/delete pods and get/patch deployments,
in the sitewatch namespace. Compared to the docker socket (= root on the host) that's
a lot less dangerous if the remediator gets compromised.
"""

import json
import os
import time

from kubernetes import client, config

NAMESPACE = os.environ.get("POD_NAMESPACE", "sitewatch")
DEPLOYMENT = os.environ.get("DEMO_DEPLOYMENT", "sitewatch-demo")
IMAGE = os.environ.get("DEMO_IMAGE", "sitewatch-demo")
HISTORY_ANNOTATION = "sitewatch/deploy-history"


class K8sDemoApp:
    def __init__(self, apps=None, core=None):
        if apps is None or core is None:
            config.load_incluster_config()
        self.apps = apps or client.AppsV1Api()
        self.core = core or client.CoreV1Api()

    # ---- deployment history, kept as an annotation on the deployment ----

    def _deployment(self):
        return self.apps.read_namespaced_deployment(DEPLOYMENT, NAMESPACE)

    def history(self) -> list[dict]:
        annotations = self._deployment().metadata.annotations or {}
        return json.loads(annotations.get(HISTORY_ANNOTATION, "[]"))

    def current_version(self) -> str | None:
        h = self.history()
        if h:
            return h[-1]["version"]
        image = self._deployment().spec.template.spec.containers[0].image
        return image.rsplit(":", 1)[-1]

    def last_deploy_time(self) -> float | None:
        h = self.history()
        return h[-1]["ts"] if h else None

    def previous_good_version(self) -> str | None:
        h = self.history()
        current = self.current_version()
        for entry in reversed(h[:-1]):
            if entry["version"] != current and not entry.get("bad"):
                return entry["version"]
        return None

    def _patch(self, version: str | None, history: list[dict]) -> None:
        body = {"metadata": {"annotations": {HISTORY_ANNOTATION: json.dumps(history)}}}
        if version:
            body["spec"] = {
                "template": {
                    "spec": {"containers": [{"name": "demo", "image": f"{IMAGE}:{version}"}]}
                }
            }
        self.apps.patch_namespaced_deployment(DEPLOYMENT, NAMESPACE, body)

    # ---- actions ----

    def deploy(self, version: str, reason: str = "manual") -> dict:
        history = self.history()
        if not history:
            # first deploy through the remediator: remember what was running before
            history.append(
                {"version": self.current_version(), "ts": time.time(), "reason": "initial"}
            )
        entry = {"version": version, "ts": time.time(), "reason": reason}
        history.append(entry)
        self._patch(version, history[-20:])
        return entry

    def rollback(self) -> dict:
        bad = self.current_version()
        target = self.previous_good_version()
        if target is None:
            raise RuntimeError("no previous good version to roll back to")
        history = self.history()
        history[-1]["bad"] = True
        self._patch(None, history)
        entry = self.deploy(target, reason=f"rollback from {bad}")
        return {**entry, "from": bad}

    def restart(self) -> dict:
        # delete the pod, the deployment's ReplicaSet creates a new one right away
        pods = self.core.list_namespaced_pod(NAMESPACE, label_selector=f"app={DEPLOYMENT}")
        names = [p.metadata.name for p in pods.items]
        for name in names:
            self.core.delete_namespaced_pod(name, NAMESPACE, grace_period_seconds=0)
        return {"deleted_pods": names}

    def cleanup_disk(self) -> dict:
        # /data is an emptyDir, a new pod gets an empty one. cleaning up inside the running pod
        # would need pods/exec, which is basically a shell in any pod -> not giving that
        return self.restart()

    def ensure_running(self, default_version: str = "1.0") -> None:
        pass  # kubernetes does this itself
