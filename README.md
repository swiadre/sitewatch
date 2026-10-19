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

## Tests

```bash
pytest
ruff check .
```
