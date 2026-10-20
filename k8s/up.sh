#!/usr/bin/env bash
# local kubernetes cluster (kind) with the whole sitewatch stack
#   ./k8s/up.sh        create cluster + build + deploy
#   ./k8s/down.sh      delete the cluster
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=sitewatch

if ! kind get clusters | grep -qx "$CLUSTER"; then
  kind create cluster --name "$CLUSTER" --config k8s/kind.yaml
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null

echo "--- building images"
docker build -q -t sitewatch-prober:dev .
docker build -q -t sitewatch-remediator:dev -f remediation/Dockerfile .
docker build -q -t sitewatch-demo:1.0 --build-arg APP_VERSION=1.0 demo/
docker build -q -t sitewatch-demo:1.1-bad --build-arg APP_VERSION=1.1-bad demo/

echo "--- loading images into kind (there's no registry)"
kind load docker-image --name "$CLUSTER" \
  sitewatch-prober:dev sitewatch-remediator:dev sitewatch-demo:1.0 sitewatch-demo:1.1-bad

# helper image for the latency chaos test (tc). `kind load` fails for this multi-arch image,
# so pull it on the node. if it's missing, the debug container pulls it during the test
# and the fault starts ~1 min late (that broke my first measurement)
docker exec "$CLUSTER-control-plane" crictl pull nicolaka/netshoot:v0.13 >/dev/null

kubectl create namespace sitewatch --dry-run=client -o yaml | kubectl apply -f - >/dev/null
if [ -f deploy/.env ] && [ "${NO_TELEGRAM:-}" != "1" ]; then
  # only the 2 telegram values, not the whole .env
  grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' deploy/.env > /tmp/sitewatch-telegram.env || true
  kubectl -n sitewatch create secret generic telegram --from-env-file=/tmp/sitewatch-telegram.env \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  rm -f /tmp/sitewatch-telegram.env
fi

echo "--- deploying"
kubectl kustomize --load-restrictor LoadRestrictionsNone k8s | kubectl apply -f -
kubectl -n sitewatch rollout status deploy --timeout=180s

cat <<MSG

done:
  grafana      http://localhost:3002
  prometheus   http://localhost:9092
  remediator   http://localhost:9002/status
  demo app     http://localhost:8082
MSG
