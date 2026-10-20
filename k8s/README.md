# sitewatch on Kubernetes (kind)

The same stack as `deploy/docker-compose.yml`, running on a local [kind](https://kind.sigs.k8s.io/)
cluster. Free, nothing in the cloud.

```bash
./k8s/up.sh      # create cluster, build images, load them into kind, deploy
./k8s/down.sh    # delete the cluster
```

| | |
|---|---|
| Grafana | http://localhost:3002 |
| Prometheus | http://localhost:9092 |
| remediator | http://localhost:9002/status |
| demo app | http://localhost:8082 |

Services are `NodePort`s mapped to the host in [`kind.yaml`](kind.yaml). I didn't use
`kubectl port-forward`, because it breaks when the pod behind it is deleted, and that's
exactly what the chaos tests do.

## What's different from docker compose

- **Same config files.** `kustomization.yaml` builds ConfigMaps from the files in `deploy/`
  (Prometheus rules, Alertmanager, Grafana dashboard). Service names are the same as the compose
  service names, so no config needs changing.
- **Remediator permissions.** In docker compose the remediator has the Docker socket, which
  is root on the host. Here it has its own ServiceAccount with a Role
  ([`remediator.yaml`](remediator.yaml)) that can only:
  - get/list/delete pods in the `sitewatch` namespace (restart = delete the pod)
  - get/patch **one** deployment, `sitewatch-demo` (deploy/rollback = change the image tag)

  No `pods/exec` (that would be a shell in any pod), so "clean up the disk" is done by
  deleting the pod. `/data` is an `emptyDir`, and a new pod gets an empty one.
- **Liveness probe.** The demo app has `livenessProbe` on `/healthz`. `/healthz` takes the same
  lock as normal requests, so a deadlock makes it hang too, and the kubelet restarts the
  container. It deliberately doesn't check the version or the disk, because restarting
  doesn't fix those.
- **Deploy history** is kept as an annotation on the deployment (`sitewatch/deploy-history`).

## Chaos tests

```bash
CHAOS_TARGET=k8s python -m chaos.runner all --runs 10
python -m chaos.report --k8s
```

The remediator's safety limits have to be raised for that, same as with docker:
`kubectl -n sitewatch set env deploy/remediator MAX_ACTIONS_PER_HOUR=1000 ACTION_COOLDOWN_SECONDS=0`
(and back to `3` / `120` afterwards).

Results and the comparison with docker are in [`chaos/README.md`](../chaos/README.md#docker-vs-kubernetes).
