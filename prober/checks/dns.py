import asyncio
import socket
import time
from dataclasses import dataclass, field


@dataclass
class DnsResult:
    ok: bool
    duration_ms: float | None = None
    addresses: list[str] = field(default_factory=list)
    error: str | None = None


async def check_dns(hostname: str) -> DnsResult:
    """Resolve the hostname and measure how long it takes."""
    loop = asyncio.get_running_loop()
    start = time.perf_counter()
    try:
        infos = await loop.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return DnsResult(ok=False, error=f"gaierror: {e.strerror}")
    duration_ms = (time.perf_counter() - start) * 1000

    # getaddrinfo returns duplicates (one per protocol), keep unique ips
    addresses = sorted({info[4][0] for info in infos})
    return DnsResult(ok=bool(addresses), duration_ms=round(duration_ms, 1), addresses=addresses)
