import time
from dataclasses import dataclass

import httpx


@dataclass
class HttpResult:
    ok: bool
    status_code: int | None = None
    duration_ms: float | None = None
    text_found: bool | None = None
    error: str | None = None


async def check_http(
    client: httpx.AsyncClient,
    url: str,
    expected_text: str | None = None,
    timeout: float | None = None,
) -> HttpResult:
    """GET the url and check status code, response time and (optionally) page content."""
    start = time.perf_counter()
    try:
        kwargs = {"timeout": timeout} if timeout is not None else {}
        resp = await client.get(url, follow_redirects=True, **kwargs)
    except httpx.HTTPError as e:
        # timeouts, connection refused, bad TLS etc. all end up here
        return HttpResult(ok=False, error=type(e).__name__)
    duration_ms = (time.perf_counter() - start) * 1000

    text_found = None
    if expected_text is not None:
        text_found = expected_text in resp.text

    ok = 200 <= resp.status_code < 400 and text_found is not False
    return HttpResult(
        ok=ok,
        status_code=resp.status_code,
        duration_ms=round(duration_ms, 1),
        text_found=text_found,
    )
