# sitewatch

Small monitoring + SLO project I'm building to learn how Google-style SRE works in practice.

It probes 3 real production sites every 30 seconds (HTTP, TLS, DNS) and (later) exports
metrics to Prometheus, computes SLOs / error budgets and tries to fix known failures by itself.

**Status:** work in progress — week 2 (metrics + dashboards).

## Running locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m prober
```

## Running with Docker (prober + Prometheus + Grafana)

```bash
cd deploy
docker compose up -d --build
```

- prober metrics: http://localhost:8000/metrics
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (dashboard "sitewatch - overview")

If port 3000 is taken: `GRAFANA_PORT=3001 docker compose up -d`

## Tests

```bash
pytest
ruff check .
```
