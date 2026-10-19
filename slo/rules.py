"""Generates Prometheus recording + alerting rules from slo/slos.yaml.

usage: python -m slo.rules > deploy/prometheus/rules/slo.rules.yml

Writing these by hand for 3 sites x 2 SLOs x 8 windows was getting really error prone,
so this script does it (similar idea to tools like sloth / pyrra, but way simpler).
"""

import sys
from pathlib import Path

import yaml

from slo.budget import BURN_RATE_ALERTS, error_budget

SLOS_FILE = Path(__file__).parent / "slos.yaml"
WINDOWS = ["5m", "30m", "1h", "2h", "6h", "1d", "3d", "30d"]
LONG_WINDOWS = sorted({w for w, _, _, _ in BURN_RATE_ALERTS}, key=WINDOWS.index)
WINDOW_SECONDS = {
    "5m": 300,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "6h": 21600,
    "1d": 86400,
    "3d": 259200,
    "30d": 2592000,
}


def load_slos(path: Path = SLOS_FILE) -> list[dict]:
    """Returns a flat list like [{"site": "x", "slo": "availability", "objective": 0.999}, ...]"""
    raw = yaml.safe_load(path.read_text())
    defaults = raw.get("defaults", {})
    common = {
        "probe_interval_seconds": raw.get("probe_interval_seconds", 30),
        "min_data_fraction": raw.get("min_data_fraction", 0.5),
    }
    result = []
    for site, overrides in raw["sites"].items():
        overrides = overrides or {}
        for kind, default in defaults.items():
            slo = {**common, **default, **overrides.get(kind, {}), "site": site, "slo": kind}
            error_budget(slo["objective"])  # validates the objective
            result.append(slo)
    return result


def format_le(threshold: float) -> str:
    # prometheus_client writes bucket labels like "1.5" and "1.0", not "1"
    return str(float(threshold))


def error_ratio_expr(slo: dict, window: str) -> str:
    site = slo["site"]
    if slo["slo"] == "availability":
        return (
            f'sum(rate(probes_total{{site="{site}",result="failure"}}[{window}]))\n'
            f'/\nsum(rate(probes_total{{site="{site}"}}[{window}]))'
        )
    if slo["slo"] == "latency":
        le = format_le(slo["threshold_seconds"])
        return (
            f"1 - (\n"
            f'  sum(rate(probe_duration_seconds_bucket{{site="{site}",le="{le}"}}[{window}]))\n'
            f"  /\n"
            f'  sum(rate(probe_duration_seconds_count{{site="{site}"}}[{window}]))\n'
            f")"
        )
    raise ValueError(f"unknown slo type {slo['slo']}")


def events_expr(slo: dict, window: str) -> str:
    """How many probes (= SLI events) we actually have in the window."""
    site = slo["site"]
    metric = "probes_total" if slo["slo"] == "availability" else "probe_duration_seconds_count"
    return f'sum(increase({metric}{{site="{site}"}}[{window}]))'


def min_events(slo: dict, window: str) -> int:
    expected = WINDOW_SECONDS[window] / slo.get("probe_interval_seconds", 30)
    return int(expected * slo.get("min_data_fraction", 0.5))


def recording_rules(slo: dict) -> list[dict]:
    labels = {"site": slo["site"], "slo": slo["slo"]}
    rules = [
        {
            "record": f"slo:sli_error:ratio_rate{w}",
            "expr": error_ratio_expr(slo, w),
            "labels": labels,
        }
        for w in WINDOWS
    ]
    rules += [
        {"record": f"slo:sli_events:increase{w}", "expr": events_expr(slo, w), "labels": labels}
        for w in LONG_WINDOWS
    ]
    rules.append(
        {"record": "slo:objective:ratio", "expr": f"vector({slo['objective']})", "labels": labels}
    )
    rules.append(
        {
            "record": "slo:error_budget_remaining:ratio",
            "expr": (
                f'1 - (slo:sli_error:ratio_rate30d{{site="{slo["site"]}",slo="{slo["slo"]}"}}'
                f" / {error_budget(slo['objective']):g})"
            ),
            "labels": labels,
        }
    )
    return rules


def alert_rules(slo: dict) -> list[dict]:
    site, kind = slo["site"], slo["slo"]
    budget = error_budget(slo["objective"])
    sel = f'{{site="{site}",slo="{kind}"}}'

    alerts = []
    for severity in ("page", "ticket"):
        conditions = []
        for long_w, short_w, factor, sev in BURN_RATE_ALERTS:
            if sev != severity:
                continue
            threshold = round(factor * budget, 6)
            if threshold >= 1:
                # e.g. latency 90% -> 14.4 * 0.1 = 1.44, error ratio can never be >144%,
                # so this condition could never fire. skip it instead of pretending
                continue
            # the last line: only alert if we have at least half of the probes we expect in
            # the long window. with gaps in the data (prober down, laptop asleep) one failed
            # probe out of 20 looks like a 5% error rate -> false page (postmortems/2026-10-19)
            conditions.append(
                f"(slo:sli_error:ratio_rate{long_w}{sel} > {threshold:g}\n"
                f" and slo:sli_error:ratio_rate{short_w}{sel} > {threshold:g}\n"
                f" and slo:sli_events:increase{long_w}{sel} >= {min_events(slo, long_w)})"
            )
        if not conditions:
            continue
        name = "Fast" if severity == "page" else "Slow"
        alerts.append(
            {
                "alert": f"ErrorBudgetBurn{name}",
                "expr": "\nor\n".join(conditions),
                "for": "2m" if severity == "page" else "15m",
                "labels": {"severity": severity, "site": site, "slo": kind},
                "annotations": {
                    "summary": f"{site}: {kind} SLO is burning error budget too fast",
                    "description": (
                        "error ratio {{ $value | humanizePercentage }}, "
                        f"objective {slo['objective']:.3%}"
                    ),
                },
            }
        )
    return alerts


def build_rules(slos: list[dict]) -> dict:
    groups = []
    for slo in slos:
        groups.append(
            {
                "name": f"slo-{slo['site']}-{slo['slo']}",
                "rules": recording_rules(slo) + alert_rules(slo),
            }
        )
    return {"groups": groups}


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        # no &id001 / *id001 anchors in the output, they're confusing to read
        return True


def _str_presenter(dumper, data):
    # multi-line promql looks much nicer as a | block
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_presenter)


def main() -> None:
    rules = build_rules(load_slos())
    sys.stdout.write("# GENERATED by `python -m slo.rules` from slo/slos.yaml - don't edit!\n")
    yaml.dump(rules, sys.stdout, Dumper=_Dumper, sort_keys=False, width=120)


if __name__ == "__main__":
    main()
