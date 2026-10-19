import httpx

from prober.checks.http import check_http


def make_client(handler) -> httpx.AsyncClient:
    # MockTransport lets us fake a server without any network
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_ok_with_expected_text():
    async with make_client(lambda req: httpx.Response(200, text="<h1>Hello KuponRadar</h1>")) as c:
        result = await check_http(c, "https://example.com", expected_text="KuponRadar")
    assert result.ok
    assert result.status_code == 200
    assert result.text_found is True
    assert result.duration_ms is not None


async def test_missing_text_is_failure():
    async with make_client(lambda req: httpx.Response(200, text="maintenance mode")) as c:
        result = await check_http(c, "https://example.com", expected_text="KuponRadar")
    assert not result.ok
    assert result.text_found is False


async def test_500_is_failure():
    async with make_client(lambda req: httpx.Response(500)) as c:
        result = await check_http(c, "https://example.com")
    assert not result.ok
    assert result.status_code == 500


async def test_no_expected_text_skips_content_check():
    async with make_client(lambda req: httpx.Response(204)) as c:
        result = await check_http(c, "https://example.com")
    assert result.ok
    assert result.text_found is None


async def test_follows_redirect():
    def handler(req):
        if req.url.path == "/":
            return httpx.Response(301, headers={"Location": "https://example.com/home"})
        return httpx.Response(200, text="home")

    async with make_client(handler) as c:
        result = await check_http(c, "https://example.com/", expected_text="home")
    assert result.ok
    assert result.status_code == 200


async def test_connection_error():
    def handler(req):
        raise httpx.ConnectError("connection refused")

    async with make_client(handler) as c:
        result = await check_http(c, "https://example.com")
    assert not result.ok
    assert result.error == "ConnectError"
    assert result.status_code is None


async def test_timeout():
    def handler(req):
        raise httpx.ReadTimeout("too slow")

    async with make_client(handler) as c:
        result = await check_http(c, "https://example.com")
    assert not result.ok
    assert result.error == "ReadTimeout"
