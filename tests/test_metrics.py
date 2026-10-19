from prometheus_client import REGISTRY

from prober import metrics
from prober.checks.dns import DnsResult
from prober.checks.http import HttpResult
from prober.checks.tls import TlsResult
from prober.config import Site
from prober.main import SiteReport


def make_report(name: str, http_ok: bool = True) -> SiteReport:
    return SiteReport(
        site=Site(name=name, url="https://example.com"),
        http=HttpResult(ok=http_ok, status_code=200 if http_ok else 503, duration_ms=420),
        tls=TlsResult(ok=True, days_left=55.5),
        dns=DnsResult(ok=True, duration_ms=4),
    )


def value(name: str, **labels) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def test_record_success():
    metrics.record(make_report("metrics-ok"))
    assert value("probe_success", site="metrics-ok") == 1
    assert value("tls_cert_days_left", site="metrics-ok") == 55.5
    assert value("probe_http_status_code", site="metrics-ok") == 200
    assert value("probes_total", site="metrics-ok", result="success") == 1
    # 0.42s should land in the 0.5 bucket but not in 0.25
    assert value("probe_duration_seconds_bucket", site="metrics-ok", le="0.5") == 1
    assert value("probe_duration_seconds_bucket", site="metrics-ok", le="0.25") == 0


def test_record_failure():
    metrics.record(make_report("metrics-bad", http_ok=False))
    assert value("probe_success", site="metrics-bad") == 0
    assert value("probes_total", site="metrics-bad", result="failure") == 1


def test_init_site_creates_failure_counter():
    metrics.init_site("metrics-new")
    assert value("probes_total", site="metrics-new", result="failure") == 0
    assert value("probes_total", site="metrics-new", result="success") == 0
