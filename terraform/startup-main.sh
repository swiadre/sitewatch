#!/bin/bash
# runs on every boot of the main VM
set -euo pipefail

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

if [ ! -d /opt/sitewatch ]; then
  git clone ${repo_url} /opt/sitewatch
fi
cd /opt/sitewatch && git pull --ff-only

# regional probers from terraform -> prometheus file_sd format
echo '${probers}' > deploy/prometheus/remote-probers.json

# secrets (telegram token) are NOT in terraform state, they live in Secret Manager
# or are copied to deploy/.env by hand once
cd deploy && docker compose up -d --build
