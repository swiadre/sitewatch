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
