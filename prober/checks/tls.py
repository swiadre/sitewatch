import asyncio
import ssl
import time
from dataclasses import dataclass


@dataclass
class TlsResult:
    ok: bool
    days_left: float | None = None
    error: str | None = None


def days_until_expiry(cert: dict, now: float | None = None) -> float:
    """cert is the dict from getpeercert(), notAfter looks like 'Jun  1 12:00:00 2026 GMT'"""
    expires = ssl.cert_time_to_seconds(cert["notAfter"])
    if now is None:
        now = time.time()
    return (expires - now) / 86400


async def check_tls(hostname: str, port: int = 443, min_days: int = 14) -> TlsResult:
    """Open a TLS connection and check how many days the certificate has left."""
    ctx = ssl.create_default_context()
    try:
        reader, writer = await asyncio.open_connection(
            hostname, port, ssl=ctx, server_hostname=hostname
        )
    except (OSError, ssl.SSLError) as e:
        return TlsResult(ok=False, error=type(e).__name__)

    try:
        cert = writer.get_extra_info("peercert")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, ssl.SSLError):
            pass  # don't care if closing fails

    if not cert:
        return TlsResult(ok=False, error="NoCertificate")

    days = days_until_expiry(cert)
    return TlsResult(ok=days >= min_days, days_left=round(days, 1))
