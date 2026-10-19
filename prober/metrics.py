from prometheus_client import Counter, Gauge, Histogram, start_http_server

# buckets picked around what I see from my laptop (~0.4s - 2s)
LATENCY_BUCKETS = (0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10)

PROBE_SUCCESS = Gauge(
    "probe_success", "1 if the last http probe of the site was ok", ["site"]
)
PROBE_DURATION = Histogram(
    "probe_duration_seconds", "HTTP response time", ["site"], buckets=LATENCY_BUCKETS
)
PROBES_TOTAL = Counter("probes_total", "Number of probes", ["site", "result"])
HTTP_STATUS = Gauge("probe_http_status_code", "Last HTTP status code (0 = no response)", ["site"])
TLS_DAYS_LEFT = Gauge("tls_cert_days_left", "Days until the TLS certificate expires", ["site"])
DNS_DURATION = Gauge("dns_lookup_duration_seconds", "Time of the last DNS lookup", ["site"])


def start_metrics_server(port: int) -> None:
    start_http_server(port)


def init_site(site: str) -> None:
    """Create the counters with 0 at startup.

    Without this probes_total{result="failure"} doesn't exist until the first failure,
    and then the SLO error ratio query returns *no data* instead of 0.
    """
    PROBES_TOTAL.labels(site, "success")
    PROBES_TOTAL.labels(site, "failure")


def record(report) -> None:
    """Update all metrics from one SiteReport."""
    site = report.site.name

    PROBE_SUCCESS.labels(site).set(1 if report.up else 0)
    PROBES_TOTAL.labels(site, "success" if report.up else "failure").inc()
    HTTP_STATUS.labels(site).set(report.http.status_code or 0)

    if report.http.duration_ms is not None:
        PROBE_DURATION.labels(site).observe(report.http.duration_ms / 1000)
    if report.tls.days_left is not None:  # None also for http-only sites
        TLS_DAYS_LEFT.labels(site).set(report.tls.days_left)
    if report.dns.duration_ms is not None:
        DNS_DURATION.labels(site).set(report.dns.duration_ms / 1000)
