#!/bin/bash
# runs on every boot of a regional prober VM
set -euo pipefail

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

if [ ! -d /opt/sitewatch ]; then
  git clone ${repo_url} /opt/sitewatch
fi
cd /opt/sitewatch && git pull --ff-only

docker build -t sitewatch-prober .
docker rm -f prober 2>/dev/null || true
docker run -d --name prober --restart unless-stopped -p 8000:8000 sitewatch-prober
