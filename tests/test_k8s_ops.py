import json
from types import SimpleNamespace

from remediation.k8s_ops import HISTORY_ANNOTATION, K8sDemoApp


class FakeApps:
    """Just enough of AppsV1Api: one deployment, patches are merged in."""

    def __init__(self, image="sitewatch-demo:1.0"):
        self.annotations = {}
        self.image = image
        self.patches = []

    def read_namespaced_deployment(self, name, ns):
        container = SimpleNamespace(image=self.image)
        return SimpleNamespace(
            metadata=SimpleNamespace(annotations=dict(self.annotations)),
            spec=SimpleNamespace(
                template=SimpleNamespace(spec=SimpleNamespace(containers=[container]))
            ),
        )

    def patch_namespaced_deployment(self, name, ns, body):
        self.patches.append(body)
        self.annotations.update(body["metadata"]["annotations"])
        if "spec" in body:
            self.image = body["spec"]["template"]["spec"]["containers"][0]["image"]


class FakeCore:
    def __init__(self):
        self.deleted = []

    def list_namespaced_pod(self, ns, label_selector):
        return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name="demo-abc"))])

    def delete_namespaced_pod(self, name, ns, grace_period_seconds):
        self.deleted.append(name)


def test_deploy_then_rollback():
    apps = FakeApps()
    demo = K8sDemoApp(apps=apps, core=FakeCore())
    assert demo.current_version() == "1.0"

    demo.deploy("1.1-bad")
    assert apps.image == "sitewatch-demo:1.1-bad"
    assert demo.previous_good_version() == "1.0"

    result = demo.rollback()
    assert result["from"] == "1.1-bad"
    assert apps.image == "sitewatch-demo:1.0"
    history = json.loads(apps.annotations[HISTORY_ANNOTATION])
    assert [h["version"] for h in history] == ["1.0", "1.1-bad", "1.0"]
    assert history[1]["bad"] is True


def test_restart_deletes_pods():
    core = FakeCore()
    demo = K8sDemoApp(apps=FakeApps(), core=core)
    assert demo.restart() == {"deleted_pods": ["demo-abc"]}
    assert core.deleted == ["demo-abc"]
