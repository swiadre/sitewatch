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

## Results

With auto-remediation, 10 valid runs per scenario (Oct 2026, on my laptop, colima VM):

| scenario | mode | runs | recovered | MTTD mean | MTTD median | MTTR mean | MTTR median | MTTR max | fixed by |
|---|---|---|---|---|---|---|---|---|---|
| kill | auto | 10 | 10/10 | 18.4 s | 18.4 s | 18.6 s | 18.6 s | 19.1 s | restart 10× |
| hang | auto | 10 | 10/10 | 23.5 s | 23.4 s | 23.9 s | 23.9 s | 24.3 s | restart 10× |
| latency | auto | 10 | 10/10 | 22.7 s | 22.4 s | 23.2 s | 22.9 s | 24.8 s | restart 10× |
| disk | auto | 10 | 10/10 | 17.6 s | 17.6 s | 17.8 s | 17.6 s | 18.1 s | cleanup_disk 10× |
| bad_deploy | auto | 10 | 10/10 | 23.0 s | 23.1 s | 23.5 s | 23.7 s | 24.0 s | rollback 10× |

Without auto-remediation (a human fixes it): not measured.

Raw data for every run is in [`results/`](results/) (one JSON line per run).

## Docker vs Kubernetes

The same 5 scenarios against the [kind cluster](../k8s/), 10 valid runs each
(`CHAOS_TARGET=k8s`):

| scenario | mode | runs | recovered | MTTD mean | MTTD median | MTTR mean | MTTR median | MTTR max | fixed by |
|---|---|---|---|---|---|---|---|---|---|
| kill | auto | 10 | 10/10 | - | - | 0.7 s | 0.0 s | 1.8 s | kubernetes itself 4×, no visible downtime 6× |
| hang | auto | 10 | 10/10 | 18.5 s | 18.5 s | 18.0 s | 18.3 s | 18.7 s | k8s livenessProbe 8×, kubernetes itself 2× |
| latency | auto | 10 | 10/10 | 25.5 s | 26.1 s | 27.4 s | 27.5 s | 31.0 s | restart 10× |
| disk | auto | 10 | 10/10 | 18.5 s | 17.7 s | 19.9 s | 19.2 s | 23.9 s | cleanup_disk 10× |
| bad_deploy | auto | 10 | 10/10 | 21.7 s | 22.2 s | 23.3 s | 23.9 s | 24.6 s | rollback 10× |

Side by side (mean MTTR):

| scenario | docker + remediator | kubernetes | who fixed it in kubernetes |
|---|---|---|---|
| kill | 18.6 s | **0.7 s** | the ReplicaSet (6 of 10 runs had no failed check at all) |
| hang | 23.9 s | **18.0 s** | the `livenessProbe` (~15 s), before my alert even fired |
| latency | 23.2 s | 27.4 s | remediator (delete pod → new network namespace) |
| disk | 17.8 s | 19.9 s | remediator (delete pod → new empty `emptyDir`) |
| bad_deploy | 23.5 s | 23.3 s | remediator (rollback = patch the image tag) |

What I took from it:
- **For crashes and hangs, the platform beats my remediator.** Kubernetes replaces a deleted
  pod in under 2 s, before any alert can fire. The liveness probe restarts a deadlocked
  container ~15 s in, while my alert needs ~18 s (probe + scrape + `for: 10s`). In 2 hang
  runs the remediator restarted a pod that was already fixed (harmless, but useless). On
  Kubernetes I'd remove `remediation: restart` from `DemoUnresponsive` and keep it as a
  page only.
- **Kubernetes can't fix the rest.** A bad version, a full disk and a slow network all
  still need something that knows about the app. That's where the remediator is still needed.
- **"Who fixed it" needs evidence, not timestamps.** My first version compared timestamps and
  got it wrong (it even said "kubernetes" for docker runs). The final version uses the
  kubelet's "failed liveness probe, will be restarted" events. Kubernetes merges repeated
  events (`count: 5`, only first and last timestamp), so for 2 runs there's no event of their
  own. They're counted as "kubernetes itself", because the app came back without any
  remediator action.
- **My laptop sleeping wrecked 11 of the k8s runs** (the lid was closed or the battery was low).
  One of them even made me believe in a keep-alive bug that didn't exist: the "46 s delay"
  was exactly the time the laptop woke up. Every run was checked against `pmset -g log`,
  invalid ones are kept in the raw data with the reason, and I ran replacements.

## What the chaos tests found (bugs in my own setup)

The point of running every scenario 10 times wasn't only the numbers. The repeated runs
found 2 problems that a single manual test didn't show:

1. **Alertmanager added up to 60 s of delay.** In the first series MTTD for `kill` went
   from ~27 s in runs 1-2 to a very stable ~38 s from run 3 on. Prometheus fired the alert
   after ~20 s every time, but the webhook arrived later. After an alert resolves, its group
   in Alertmanager still exists for a while (Prometheus keeps re-sending "resolved"), so the
   next alert joins the existing group and waits for the next `group_interval` tick (1 min)
   instead of `group_wait` (5 s). Runs started every ~2 min, so they were in phase with that
   tick. Fix: a separate route for alerts with a `remediation` label, with `group_wait: 0s`
   and `group_interval: 5s`. MTTD went from ~38 s to ~18 s. Old runs:
   [`results/v1-group-interval-1m/`](results/v1-group-interval-1m/).

2. **The first bad deploy was detected 10 s later than the rest.** `DemoErrorsAfterDeploy`
   only fires within 15 min after a deploy, and the deploy timestamp comes from the
   remediator, which Prometheus scraped every 15 s. In runs 2-10 the rollback from the
   previous run had already "opened" the 15 min window, so they looked faster than a real
   bad deploy (which usually comes after a long quiet time). Fix: scrape the remediator every
   5 s. Old runs: [`results/v2-remediator-scrape-15s/`](results/v2-remediator-scrape-15s/).
   The new runs still have a small bias (≤ 5 s) for the same reason, because I can't wait
   15 min between runs.

Also: 3 `latency` runs were invalid because my laptop went to sleep in the middle of them
(one showed MTTD = 279 s). I checked every run against the macOS power log
(`pmset -g log`). The affected runs are still in the raw data with `"invalid": "<reason>"`,
the report skips them, and I ran 3 replacement runs.

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
