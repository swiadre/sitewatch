import ssl

import pytest

from prober.checks.tls import check_tls, days_until_expiry


def test_days_until_expiry():
    cert = {"notAfter": "Jan 31 00:00:00 2030 GMT"}
    now = ssl.cert_time_to_seconds("Jan 21 00:00:00 2030 GMT")
    assert days_until_expiry(cert, now=now) == pytest.approx(10)


def test_expired_cert_is_negative():
    cert = {"notAfter": "Jan  1 00:00:00 2020 GMT"}
    now = ssl.cert_time_to_seconds("Jan  3 00:00:00 2020 GMT")
    assert days_until_expiry(cert, now=now) == pytest.approx(-2)


async def test_connection_refused():
    # nothing listens on port 1 on localhost
    result = await check_tls("127.0.0.1", port=1)
    assert not result.ok
    assert result.error is not None
