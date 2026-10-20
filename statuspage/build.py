"""Builds the static status page from the data branch.

python -m statuspage.build --data data/ --out public/
"""

import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path

from prober.config import load_config
from statuspage.stats import load_rows, site_summary

OBJECTIVE = 0.999
REPO = "https://github.com/swiadre/sitewatch"


def pct(x: float | None, digits: int = 2) -> str:
    return "–" if x is None else f"{x * 100:.{digits}f}%"


def ms(x: float | None) -> str:
    return "–" if x is None else f"{x:.0f} ms"


def human(td) -> str:
    minutes = int(td.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    return f"{minutes // 60} h {minutes % 60} min"


def bar_class(day: dict) -> str:
    a = day["availability"]
    if a is None:
        return "nodata"
    if a >= OBJECTIVE:
        return "ok"
    if a >= 0.99:
        return "warn"
    return "bad"


def render_site(name: str, url: str, s: dict, now: datetime) -> str:
    last = s["last"]
    if last is None:
        state, label = "nodata", "no data yet"
    elif last["up"] is None:
        state, label = "nodata", "unknown"
    elif last["up"]:
        state, label = "ok", "operational"
    else:
        state, label = "bad", "down"

    bars = "".join(
        f'<span class="bar {bar_class(d)}" title="{d["day"]}: '
        f'{pct(d["availability"])} ({d["probes"]} probes)"></span>'
        for d in s["daily"]
    )
    budget = s["budget_remaining"]
    budget_cls = "bad" if budget is not None and budget < 0 else ""
    tls = last.get("tls_days") if last else None

    return f"""
    <section class="card">
      <header>
        <div>
          <h2>{html.escape(name)}</h2>
          <a class="url" href="{html.escape(url)}">{html.escape(url.removeprefix("https://"))}</a>
        </div>
        <span class="pill {state}">{label}</span>
      </header>
      <div class="bars" aria-label="availability per day, last 30 days">{bars}</div>
      <div class="bars-legend"><span>30 days ago</span><span>today</span></div>
      <dl class="stats">
        <div><dt>24 h</dt><dd>{pct(s["availability_24h"])}</dd></div>
        <div><dt>7 days</dt><dd>{pct(s["availability_7d"])}</dd></div>
        <div><dt>30 days</dt><dd>{pct(s["availability_30d"], 3)}</dd></div>
        <div><dt>error budget left</dt><dd class="{budget_cls}">{pct(budget, 1)}</dd></div>
        <div><dt>p50 / p95</dt><dd>{ms(s["p50_ms"])} / {ms(s["p95_ms"])}</dd></div>
        <div><dt>TLS cert</dt><dd>{"–" if tls is None else f"{tls:.0f} days"}</dd></div>
      </dl>
    </section>"""


def render_incidents(summaries: dict, now: datetime) -> str:
    items = []
    for name, s in summaries.items():
        for inc in s["incidents"]:
            items.append((inc.start, name, inc))
    if not items:
        return '<p class="muted">No incidents in the last 30 days.</p>'
    rows = []
    for start, name, inc in sorted(items, key=lambda x: x[0], reverse=True)[:30]:
        ongoing = '<span class="pill bad">ongoing</span>' if inc.end is None else ""
        errors = ", ".join(sorted(html.escape(str(e)) for e in inc.errors))
        rows.append(
            f"<tr><td>{start:%Y-%m-%d %H:%M} UTC</td><td>{html.escape(name)}</td>"
            f"<td>{human(inc.duration(now))} {ongoing}</td><td>{inc.probes}</td>"
            f"<td><code>{errors}</code></td></tr>"
        )
    return (
        "<table><thead><tr><th>start</th><th>site</th><th>duration (approx.)</th>"
        "<th>failed probes</th><th>error</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def render(summaries: dict, urls: dict, now: datetime) -> str:
    states = [s["last"]["up"] if s["last"] else None for s in summaries.values()]
    if any(st is False for st in states):
        down = [n for n, s in summaries.items() if s["last"] and s["last"]["up"] is False]
        banner = ("bad", f"Down: {', '.join(down)}")
    elif all(st is True for st in states):
        banner = ("ok", "All sites operational")
    else:
        banner = ("nodata", "Waiting for data")

    coverage = [s["coverage"] for s in summaries.values() if s["coverage"] is not None]
    data_days = max((s["data_days"] for s in summaries.values()), default=0)
    cards = "".join(render_site(n, urls[n], s, now) for n, s in summaries.items())

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sitewatch status</title>
<style>
:root {{
  --bg: #f6f7f9; --card: #ffffff; --text: #1b1f24; --muted: #5f6b7a; --line: #e3e6ea;
  --ok: #1f9d55; --warn: #d97706; --bad: #dc2626; --nodata: #cbd2d9;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0f1216; --card: #171b21; --text: #e6e9ed; --muted: #9aa5b1; --line: #262c34;
    --ok: #34c77b; --warn: #f0a92e; --bad: #f05252; --nodata: #3a424d;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 860px; margin: 0 auto; padding: 32px 16px 48px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
h2 {{ font-size: 17px; margin: 0; }}
h3 {{ font-size: 16px; margin: 32px 0 12px; }}
a {{ color: inherit; }}
.muted, .url {{ color: var(--muted); font-size: 13px; }}
.url {{ text-decoration: none; }}
.banner {{ margin: 20px 0; padding: 14px 18px; border-radius: 10px; font-weight: 600;
  color: #fff; background: var(--ok); }}
.banner.bad {{ background: var(--bad); }} .banner.nodata {{ background: var(--muted); }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 18px; margin-bottom: 14px; }}
.card header {{ display: flex; justify-content: space-between; align-items: start; gap: 12px; }}
.pill {{ font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 99px;
  color: #fff; background: var(--ok); white-space: nowrap; }}
.pill.bad {{ background: var(--bad); }} .pill.nodata {{ background: var(--muted); }}
.bars {{ display: flex; gap: 3px; margin: 16px 0 4px; height: 34px; }}
.bar {{ flex: 1; border-radius: 3px; background: var(--ok); }}
.bar.warn {{ background: var(--warn); }} .bar.bad {{ background: var(--bad); }}
.bar.nodata {{ background: var(--nodata); }}
.bars-legend {{ display: flex; justify-content: space-between; color: var(--muted);
  font-size: 12px; }}
.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px 16px;
  margin: 16px 0 0; }}
.stats div {{ min-width: 0; }}
.stats dt {{ color: var(--muted); font-size: 12px; }}
.stats dd {{ margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; }}
.stats dd.bad {{ color: var(--bad); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); }}
th {{ color: var(--muted); font-weight: 500; }}
.table-wrap {{ overflow-x: auto; background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; padding: 4px 12px; }}
footer {{ margin-top: 32px; color: var(--muted); font-size: 13px; }}
footer li {{ margin-bottom: 6px; }}
@media (max-width: 560px) {{ .stats {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body>
<main>
  <h1>sitewatch status</h1>
  <div class="muted">
    updated {now:%Y-%m-%d %H:%M} UTC · SLO: {OBJECTIVE:.1%} availability / 30 days
  </div>
  <div class="banner {banner[0]}">{html.escape(banner[1])}</div>
  {cards}
  <h3>Incidents (last 30 days)</h3>
  <div class="table-wrap">{render_incidents(summaries, now)}</div>
  <footer>
    <h3>How this is measured</h3>
    <ul>
      <li>Every ~5 minutes a GitHub Actions job requests each site and checks the HTTP status,
        that the expected text is on the page, response time, TLS certificate and DNS.</li>
      <li>GitHub runs scheduled jobs on a best-effort basis, so some runs are late or skipped.
        Data coverage so far: {pct(min(coverage) if coverage else None, 0)} of expected probes
        over {data_days:.1f} days. One failed probe ≈ 5 min of downtime, so short outages
        can be missed.</li>
      <li>If a site fails and a canary URL fails too, the probe counts as "unknown" (our
        network, not the site) and is not included in availability.</li>
      <li>Runners are in GitHub's cloud (usually the US), so response times include
        transatlantic latency.</li>
    </ul>
    <p><a href="{REPO}">source code</a> · <a href="status.json">status.json</a></p>
  </footer>
</main>
</body>
</html>
"""


def to_json(summaries: dict, now: datetime) -> dict:
    out = {"updated": now.isoformat(timespec="seconds"), "objective": OBJECTIVE, "sites": {}}
    for name, s in summaries.items():
        out["sites"][name] = {
            "up": s["last"]["up"] if s["last"] else None,
            "availability_24h": s["availability_24h"],
            "availability_7d": s["availability_7d"],
            "availability_30d": s["availability_30d"],
            "error_budget_remaining": s["budget_remaining"],
            "p50_ms": s["p50_ms"],
            "p95_ms": s["p95_ms"],
            "incidents_30d": len(s["incidents"]),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="public")
    args = parser.parse_args()

    now = datetime.now(UTC)
    config = load_config()
    rows = load_rows(Path(args.data))
    summaries = {
        site.name: site_summary([r for r in rows if r["site"] == site.name], now)
        for site in config.sites
    }
    urls = {site.name: site.url for site in config.sites}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(summaries, urls, now))
    (out / "status.json").write_text(json.dumps(to_json(summaries, now), indent=2))
    print(f"built {out / 'index.html'} from {len(rows)} probes")


if __name__ == "__main__":
    main()
