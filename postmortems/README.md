# Postmortems

Every **real** incident on one of the monitored sites gets a write-up here, in the blameless
format from the [SRE book](https://sre.google/sre-book/postmortem-culture/): the point is
what to change in the system, not whose fault it was.

Chaos test runs on the demo app don't count, those are in [`chaos/`](../chaos/).
Incidents of the monitoring itself (false alarms, missed alerts) do count.

Copy [`TEMPLATE.md`](TEMPLATE.md) to `YYYY-MM-DD-short-name.md`.

| date | site | impact | summary |
|---|---|---|---|
| 2026-10-19 | kuponradar, taxnieruchomosci | none (false alarm) | [false page after my laptop woke up](2026-10-19-false-page-after-laptop-wake.md): 1 failed probe in a half-empty 1h window = 34× burn rate |
