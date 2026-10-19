# sitewatch

[![CI](https://github.com/swiadre/sitewatch/actions/workflows/ci.yml/badge.svg)](https://github.com/swiadre/sitewatch/actions/workflows/ci.yml)

Monitoring + SLOs + auto-remediation for 3 real production sites, built to learn how
Google-style SRE works in practice (SLIs/SLOs, error budgets, burn-rate alerts, chaos testing).

- probes **kuponradar.pl**, **taxnieruchomosci.pl** and **alstrategika.com** every 30 s (HTTP, TLS, DNS)
- Prometheus + Grafana dashboards, **SLOs with error budgets** and **multi-window burn-rate alerts**
- alerts go to Telegram through a small **remediator** service that also **fixes known failures by itself**
  (restart, rollback, disk cleanup) with safety limits
- **chaos tests** for 5 failure scenarios measure MTTD / MTTR with and without auto-remediation
- infrastructure as code (Terraform, GCP) + CI/CD (GitHub Actions)

![dashboard](docs/dashboard.png)

## Results

Chaos tests on the demo app: 5 failure scenarios × 10 runs each, **with auto-remediation**
([details + raw data](chaos/README.md)):

| scenario | mode | runs | recovered | MTTD mean | MTTD median | MTTR mean | MTTR median | MTTR max |
|---|---|---|---|---|---|---|---|---|
| kill | auto | 10 | 10/10 | 18.4 s | 18.4 s | 18.6 s | 18.6 s | 19.1 s |
| hang | auto | 10 | 10/10 | 23.5 s | 23.4 s | 23.9 s | 23.9 s | 24.3 s |
| latency | auto | 10 | 10/10 | 22.7 s | 22.4 s | 23.2 s | 22.9 s | 24.8 s |
| disk | auto | 10 | 10/10 | 17.6 s | 17.6 s | 17.8 s | 17.6 s | 18.1 s |
| bad_deploy | auto | 10 | 10/10 | 23.0 s | 23.1 s | 23.5 s | 23.7 s | 24.0 s |

- **50/50 failures fixed automatically**, mean time to recovery **21.4 s**, worst case 24.8 s
- MTTR is only ~0.4 s more than MTTD, so **almost all of the recovery time is detection**.
  The fix itself (restart / rollback / cleanup) takes well under a second. To go faster I'd
  need faster detection (shorter probe interval and `for:`), at the cost of more false alarms
- the repeated runs found **2 bugs in my own alerting pipeline** (Alertmanager grouping
  added 10-20 s, a 15 s scrape interval delayed bad-deploy detection), both fixed
  ([what happened](chaos/README.md#what-the-chaos-tests-found-bugs-in-my-own-setup))
- MTTR **without** automation (a human gets the Telegram alert and fixes it by hand):
  _not measured yet_, see `--mode manual` in [chaos/README.md](chaos/README.md#running)

## Architecture

```mermaid
flowchart LR
    subgraph sites[production sites]
        K[kuponradar.pl]
        T[taxnieruchomosci.pl]
        A[alstrategika.com]
    end

    D[demo app<br/>broken on purpose]

    P[prober<br/>Python asyncio] -->|HTTP/TLS/DNS every 30s| sites
    P -->|every 5s| D
    PR[probers in other regions<br/>terraform] -.-> sites

    PROM[(Prometheus<br/>SLO recording +<br/>burn-rate rules)] -->|scrape /metrics| P
    PROM -.-> PR
    PROM --> AM[Alertmanager]
    AM -->|webhook| R[remediator<br/>FastAPI]
    R -->|message| TG[Telegram]
    R -->|restart / rollback / cleanup<br/>docker API| D
    G[Grafana] --> PROM
    C[chaos scripts] -->|break| D
    C -->|measure MTTD/MTTR| R
```

| folder | what's inside |
|---|---|
| [`prober/`](prober/) | async probes (HTTP status + content, response time, TLS expiry, DNS), Prometheus metrics |
| [`slo/`](slo/) | SLO definitions, error budget math, generator for burn-rate rules. **[Why these SLOs →](slo/README.md)** |
| [`remediation/`](remediation/) | Alertmanager webhook → Telegram + automatic fixes, rate limited |
| [`demo/`](demo/) | tiny app used as a target for remediation and chaos tests |
| [`chaos/`](chaos/) | failure scenarios + MTTD/MTTR measurement. **[Details →](chaos/README.md)** |
| [`deploy/`](deploy/) | docker compose, Prometheus rules + promtool unit tests, Alertmanager, Grafana dashboard JSON |
| [`terraform/`](terraform/) | GCP: main VM, probers in 2 more regions, firewall, optional DNS |
| [`postmortems/`](postmortems/) | blameless postmortems of real incidents |

## Design decisions (short version)

- **Availability = HTTP only.** A cert expiring in 10 days or a slow DNS lookup isn't downtime
  for users, so they get their own alerts instead of eating the error budget.
- **Content check.** A suspended-hosting page also returns 200, so every site has an
  expected text that must be on the page.
- **Burn-rate alerts, not "alert on every error".** One failed probe never pages anyone
  (tested with `promtool test rules`). A full outage pages in ~1 min, slow
  degradation opens a ticket.
- **Latency SLO is based on data, not wishes.** I wanted "95% < 500 ms", measured, and
  saw it would be broken from day one. It's 90% < 1.5 s for now ([details](slo/README.md#latency-90-of-responses-under-15-s)).
- **Auto-remediation has a budget too.** Max 3 actions per hour + a 2 min cooldown per
  action. After that it stops and tells a human, so a bad fix can't loop forever.
- **Chaos only on the demo app.** I don't own the hosting of the real sites, and breaking
  production on purpose for a portfolio project would be a bad idea anyway.

## Running it

Needs Docker and Python 3.12.

```bash
cd deploy
cp .env.example .env          # optional: telegram bot token + chat id
docker compose up -d --build
```

| | |
|---|---|
| Grafana | http://localhost:3000 (dashboard "sitewatch - overview") |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |
| remediator | http://localhost:9000/status, `/events` |
| demo app | http://localhost:8081 |

If port 3000 is taken: `GRAFANA_PORT=3001 docker compose up -d`.

Telegram: create a bot with [@BotFather](https://t.me/BotFather), send it any message, get
your chat id from `https://api.telegram.org/bot<TOKEN>/getUpdates`, put both into `deploy/.env`.
Without them the remediator just prints the messages to its log.

Only the prober, without Docker:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m prober --once
```

## Tests

```bash
pytest                 # python unit tests
ruff check .
# alert rule unit tests (also run in CI):
docker run --rm --entrypoint promtool -v "$PWD/deploy/prometheus:/p:ro" -w /p/tests \
  prom/prometheus:v2.54.1 test rules slo_test.yml
```

CI runs ruff, pytest, `promtool check` + `promtool test rules`, `amtool check-config` and
`terraform validate` on every push. After CI passes on `main`, images are built and pushed
to GHCR. The deploy step to GCP is ready but switched off until the GCP project exists.

## Known limitations / what I'd do differently

- all real numbers so far come from probing **from my home network**. The regional probers
  are in Terraform but not deployed yet
- the remediator talks to the Docker socket, which is root on the host. Fine on my own
  machine, but in a real setup it'd be a k8s operator with narrow RBAC instead
- SLO windows need weeks of data to be meaningful. In the first hours a single failure looks
  much bigger than it is ([more](slo/README.md#known-limitations))
- **at 1000 sites instead of 3:** generated rules per site would explode (that's ~24 rules
  per site). I'd switch to one set of rules with `by (site)` and the objective as a recording
  rule joined in. Probers would be sharded by site hash, and Prometheus would need
  federation or something like Thanos/Mimir
