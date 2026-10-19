import asyncio
import time
from dataclasses import dataclass
from datetime import datetime

import httpx

from prober import metrics
from prober.checks.dns import DnsResult, check_dns
from prober.checks.http import HttpResult, check_http
from prober.checks.tls import TlsResult, check_tls
from prober.config import Config, Site, load_config


@dataclass
class SiteReport:
    site: Site
    http: HttpResult
    tls: TlsResult
    dns: DnsResult

    @property
    def up(self) -> bool:
        # "up" = what a user sees, so only the http check counts here.
        # a cert expiring in 10 days or a slow separate dns lookup is not downtime,
        # those get their own alerts instead
        return self.http.ok


async def with_timeout(coro, timeout: float, fail_result):
    # a safety net, httpx has its own timeout but tls/dns don't
    try:
        return await asyncio.wait_for(coro, timeout)
    except TimeoutError:
        return fail_result


async def skipped_tls() -> TlsResult:
    return TlsResult(ok=True, error="skipped")


async def probe_site(
    client: httpx.AsyncClient, site: Site, timeout: float | None = None
) -> SiteReport:
    timeout = timeout or site.timeout_seconds
    # plain http sites (like the local demo app) have no certificate to check
    tls_check = check_tls(site.hostname) if site.is_https else skipped_tls()
    http, tls, dns = await asyncio.gather(
        with_timeout(
            check_http(client, site.url, site.expected_text, timeout=timeout),
            timeout,
            HttpResult(ok=False, error="Timeout"),
        ),
        with_timeout(tls_check, timeout, TlsResult(ok=False, error="Timeout")),
        with_timeout(check_dns(site.hostname), timeout, DnsResult(ok=False, error="Timeout")),
    )
    return SiteReport(site=site, http=http, tls=tls, dns=dns)


async def probe_all(client: httpx.AsyncClient, config: Config) -> list[SiteReport]:
    return await asyncio.gather(*(probe_site(client, site) for site in config.sites))


def format_report(r: SiteReport) -> str:
    status = "UP  " if r.up else "DOWN"
    code = r.http.status_code or r.http.error
    ms = f"{r.http.duration_ms:.0f}ms" if r.http.duration_ms is not None else "-"
    tls = f"{r.tls.days_left:.0f}d" if r.tls.days_left is not None else r.tls.error
    dns = f"{r.dns.duration_ms:.0f}ms" if r.dns.duration_ms is not None else r.dns.error
    line = f"  {status} {r.site.name:<18} http={code} {ms:>7}  tls={tls}  dns={dns}"
    if r.http.text_found is False:
        line += "  (expected text missing!)"
    return line


def now() -> str:
    return f"{datetime.now():%Y-%m-%d %H:%M:%S}"


async def site_loop(client: httpx.AsyncClient, site: Site) -> None:
    """Probe one site forever. Every site has its own loop so they can have different intervals."""
    while True:
        started = time.monotonic()
        report = await probe_site(client, site)
        metrics.record(report)
        print(f"[{now()}]{format_report(report)}", flush=True)

        # sleep only for the rest of the interval so we don't drift
        elapsed = time.monotonic() - started
        await asyncio.sleep(max(0, site.interval_seconds - elapsed))


async def run(config: Config, once: bool = False) -> None:
    for site in config.sites:
        metrics.init_site(site.name)

    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        if once:
            print(f"[{now()}]")
            for r in await probe_all(client, config):
                print(format_report(r))
            return

        await asyncio.gather(
            *(site_loop(client, site) for site in config.sites)
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="sitewatch prober")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--once", action="store_true", help="probe once and exit")
    parser.add_argument("--metrics-port", type=int, default=8000, help="0 = don't expose /metrics")
    args = parser.parse_args()

    config = load_config(args.config) if args.config else load_config()
    if args.metrics_port and not args.once:
        metrics.start_metrics_server(args.metrics_port)
        print(f"metrics on http://localhost:{args.metrics_port}/metrics")
    try:
        asyncio.run(run(config, once=args.once))
    except KeyboardInterrupt:
        print("bye")
