import socket

from prober.checks.dns import check_dns


async def test_resolves_localhost():
    result = await check_dns("localhost")
    assert result.ok
    assert result.addresses
    assert result.duration_ms is not None


async def test_unknown_domain(monkeypatch):
    # don't depend on real DNS in tests, just make getaddrinfo fail
    async def fake_getaddrinfo(self, *args, **kwargs):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    import asyncio

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)
    result = await check_dns("this-does-not-exist.invalid")
    assert not result.ok
    assert "gaierror" in result.error
