import asyncio

from prober.checks.http import HttpResult
from prober.main import format_report, with_timeout


async def test_with_timeout_returns_fail_result():
    async def slow():
        await asyncio.sleep(5)

    fail = HttpResult(ok=False, error="Timeout")
    result = await with_timeout(slow(), 0.01, fail)
    assert result is fail


def test_format_report_down():
    from prober.checks.dns import DnsResult
    from prober.checks.tls import TlsResult
    from prober.config import Site
    from prober.main import SiteReport

    r = SiteReport(
        site=Site(name="test", url="https://example.com"),
        http=HttpResult(ok=False, error="ConnectError"),
        tls=TlsResult(ok=True, days_left=30),
        dns=DnsResult(ok=True, duration_ms=3),
    )
    line = format_report(r)
    assert "DOWN" in line
    assert "ConnectError" in line


def test_tls_warning_does_not_mean_down():
    from prober.checks.dns import DnsResult
    from prober.checks.tls import TlsResult
    from prober.config import Site
    from prober.main import SiteReport

    r = SiteReport(
        site=Site(name="test", url="https://example.com"),
        http=HttpResult(ok=True, status_code=200, duration_ms=300),
        tls=TlsResult(ok=False, days_left=5),
        dns=DnsResult(ok=False, error="Timeout"),
    )
    assert r.up


async def test_http_site_skips_tls():
    import httpx

    from prober.config import Site
    from prober.main import probe_site

    def handler(req):
        return httpx.Response(200, text="demo")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await probe_site(client, Site(name="d", url="http://localhost:1/"), timeout=2)
    assert report.up
    assert report.tls.error == "skipped"
    assert report.tls.days_left is None


def _client(handler):
    import httpx

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_failed_canary_means_inconclusive():
    import httpx
    from prometheus_client import REGISTRY

    from prober.config import Site
    from prober.main import probe_and_record

    def handler(req):
        raise httpx.ConnectError("no network")  # site AND canary fail

    site = Site(name="canary-test-1", url="http://localhost:1/", timeout_seconds=1)
    async with _client(handler) as c:
        result = await probe_and_record(c, site, canary_url="https://canary.example")
    assert result is None
    assert REGISTRY.get_sample_value("probes_inconclusive_total", {"site": "canary-test-1"}) == 1
    failures = REGISTRY.get_sample_value(
        "probes_total", {"site": "canary-test-1", "result": "failure"}
    )
    assert not failures  # not counted against the SLO


async def test_site_down_canary_ok_is_a_real_failure():
    import httpx

    from prober.config import Site
    from prober.main import probe_and_record

    def handler(req):
        if req.url.host == "canary.example":  # only the canary works
            return httpx.Response(204)
        return httpx.Response(503)

    site = Site(name="canary-test-2", url="http://localhost:1/", timeout_seconds=1)
    async with _client(handler) as c:
        result = await probe_and_record(c, site, canary_url="https://canary.example")
    assert result is not None
    assert not result.up


def test_report_to_dict():
    from prober.checks.dns import DnsResult
    from prober.checks.tls import TlsResult
    from prober.config import Site
    from prober.main import SiteReport, report_to_dict

    r = SiteReport(
        site=Site(name="s", url="https://example.com"),
        http=HttpResult(ok=False, status_code=200, duration_ms=120, text_found=False),
        tls=TlsResult(ok=True, days_left=40),
        dns=DnsResult(ok=True, duration_ms=3),
    )
    d = report_to_dict(r, region="test")
    assert d["up"] is False
    assert d["error"] == "TextMissing"
    assert d["region"] == "test"
    assert report_to_dict(r, region="test", inconclusive=True)["up"] is None
