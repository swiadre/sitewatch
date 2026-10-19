# 2026-10-19: False page for 2 sites after my laptop woke up

**Status:** final
**Sites:** kuponradar, taxnieruchomosci (both were actually fine)
**Duration:** 1 failed probe each at 18:39:34. False page 18:41:47 to 18:44:47, false ticket 18:54:45 to 19:47:31
**User impact:** none
**Error budget used:** none for real. On paper the 30d availability budget shows about -230%,
because one bad probe counts against only ~4 hours of data

## Summary

The whole stack runs on my laptop, and the laptop was asleep on and off during chaos tests.
It woke up at 18:39:25. 9 seconds later the HTTP probes for kuponradar and taxnieruchomosci
timed out, because the network wasn't fully up yet. Because of the sleep gaps, the 1h SLO window
had only 29 probes instead of the expected 120. So 1 failure looked like a 3.4% error rate,
a **34× burn rate**, and `ErrorBudgetBurnFast` paged for both sites. Both sites were up the
whole time.

Nobody actually got woken up (Telegram isn't configured yet, so the message only went to the
remediator log). I found it while reviewing the dashboard. With Telegram set up, this would
have been a real false page.

## Impact

- 2 false pages (`ErrorBudgetBurnFast`), 2 false tickets (`ErrorBudgetBurnSlow`)
- no impact on users of the sites
- the SLO data now contains 1 failed probe per site that wasn't a real failure. Prometheus
  data can't be edited, so it will stay in the 30 day window until it ages out

## Timeline (Europe/Warsaw)

| time | what happened |
|---|---|
| 18:34:59 | laptop goes to sleep (from `pmset -g log`) |
| 18:39:25 | laptop wakes up (DarkWake) |
| 18:39:34 | probes for kuponradar + taxnieruchomosci time out (HTTP and TLS timeout; DNS worked, 9-20 ms). alstrategika's probe ran at a slightly different moment and passed |
| 18:39:4x | `ErrorBudgetBurnFast` pending for both: 1h window = 1 failure / 29 probes = 3.4% > 1.44%, and the 5m window is also above the threshold |
| 18:40:04 | next probes: all sites OK again |
| 18:41:47 | **false page**: `ErrorBudgetBurnFast` firing for taxnieruchomosci (18:41:49 kuponradar) |
| 18:44:45 | page resolved (the failure dropped out of the 5m window) |
| 18:54:45 | **false ticket**: `ErrorBudgetBurnSlow` firing for both (1d window had the same problem) |
| ~19:38 | I notice -249% error budget on the dashboard and start investigating |
| 19:45 | fix 1 deployed: minimum-data guard on burn-rate alerts |
| 19:46:33 | ticket resolved (19:47:31 for taxnieruchomosci) after the rule reload |
| 19:47 | fix 2 deployed: canary check in the prober |

**Time to detect (by a human):** ~60 min (dashboard review; no Telegram)

## Root cause

Why did it page?
1. Because the 1h error ratio was 3.4%. **Why?** 1 failure / 29 probes.
2. Why only 29 probes in an hour? Because the laptop was asleep for most of that hour, so
   nothing was probed or scraped. **The burn-rate math assumes the window is full of data.**
   With 120 probes, 1 failure is 0.83%, which is below the 1.44% threshold, and it would have
   correctly not paged (that's exactly promtool test #1).
3. Why did the probe fail at all? Because the prober's own network wasn't ready after
   wake-up. **The prober couldn't tell "the site is down" from "I am offline".** It counted
   its own problem as the site's failure.
4. Why does it run on a laptop that sleeps? Because the GCP deployment (terraform/) isn't
   applied yet.

## What went well

- multi-window alerting did its job partly: the page resolved by itself after 3 minutes,
  once the failure dropped out of the 5m window
- all the data needed to reconstruct this was there: remediator event log, Prometheus
  history, macOS power log

## What went badly

- a single failed probe caused a page, which is exactly what the SLO alerting was designed
  to prevent. My promtool tests only covered "1 failure with full history", not
  "1 failure with gaps in the history"
- I had already noticed and documented the "little history = noisy windows" problem in
  `slo/README.md` (known limitations) but didn't do anything about it

## Where we got lucky

- Telegram wasn't set up yet, so nobody was woken up for nothing

## Action items

| action | type | status |
|---|---|---|
| burn-rate alerts require ≥ 50% of the expected probes in the long window (`min_data_fraction` in `slo/slos.yaml`) | prevent | **done**, regression test #8 in `deploy/prometheus/tests/slo_test.yml` fails on the old rules and passes on the new ones |
| prober checks a canary URL when a site fails. If the canary fails too, the result goes to `probes_inconclusive_total` instead of the SLO | prevent | **done** |
| run the stack on an always-on VM instead of a laptop (`terraform/`) | prevent | open, needs a GCP project |
| configure Telegram so pages actually reach a human | detect | open |
| deploy regional probers, so `SiteUnreachableFromOneRegion` can tell network issues from outages | detect | open (same as the VM) |
