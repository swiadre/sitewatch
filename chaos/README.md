# Chaos tests

Scripts that break the **demo app** on purpose and measure how fast the system notices
(MTTD) and how fast the app works again (MTTR), with and without auto-remediation.

The real sites (kuponradar etc.) are never touched here. Only the local `sitewatch-demo`
container, which exists for exactly this.

## Scenarios

| name | what happens | caught by | auto fix | manual fix |
|---|---|---|---|---|
| `kill` | `docker kill` (like an OOM kill / crash) | `DemoUnresponsive` | restart | `docker start` |
| `hang` | app deadlocks, process alive but no responses | `DemoUnresponsive` | restart | `docker restart` |
| `latency` | +800 ms network delay (`tc netem`) | `DemoSlow` | restart (new network namespace) | remove the qdisc |
| `disk` | `/data` filled to 100%, requests fail | `DemoDiskAlmostFull` | clean `/data/tmp` | `rm` by hand |
| `bad_deploy` | deploy of a version that returns 500 | `DemoErrorsAfterDeploy` | rollback to last good version | deploy 1.0 by hand |

Notes:
- `hang` is the interesting one: Docker's own restart policy does **not** help, because the
  process never exits. Something has to actually check if the app answers.
- `latency` + restart is a stand-in for "move the workload somewhere else" (what k8s would do).
  In real life a network problem often can't be fixed by the app owner at all.

## Definitions

- **t0** = moment the fault is injected
- **MTTD** = t0 → the remediator receives the alert from Alertmanager. That's also when the
  Telegram message goes out, so it's when a human would find out.
- **MTTR** = t0 → the demo app is healthy again, measured by the chaos script from outside
  (3 checks in a row with HTTP 200, the right text and < 1 s response time; checks every 0.5 s)

MTTD is mostly the sum of the pipeline delays:
probe every 5 s → Prometheus scrape every 5 s → rule evaluated every 5 s → `for: 10s` →
Alertmanager `group_wait: 5s` → webhook.

## Running

The remediator has safety limits (3 actions/hour, 2 min cooldown). For chaos runs they
have to be raised, otherwise run #4 gets blocked:

```bash
cd deploy
MAX_ACTIONS_PER_HOUR=1000 ACTION_COOLDOWN_SECONDS=0 docker compose up -d
cd ..

python -m chaos.runner kill --runs 10 --mode auto
python -m chaos.runner all --runs 10 --mode auto     # all scenarios, ~2.5 h
python -m chaos.report --write                       # -> results/summary.md
```

Without auto-remediation (`--mode manual`) the script turns auto-remediation off, breaks
the app, and when the alert arrives prints the command a human has to run. Run it and the
script measures how long that took:

```bash
python -m chaos.runner hang --runs 5 --mode manual
```

Between runs the script waits until the app is healthy and all old `Demo*` alerts are
resolved. Otherwise Alertmanager wouldn't send a new "firing" for the same alert group,
and the next run would never get detected.
