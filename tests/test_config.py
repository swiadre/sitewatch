import pytest

from prober.config import load_config


def test_default_config_loads():
    config = load_config()
    assert config.interval_seconds == 30
    assert len(config.sites) == 3
    assert config.sites[0].hostname == "kuponradar.pl"


def test_empty_config_fails(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("interval_seconds: 5\n")
    with pytest.raises(ValueError):
        load_config(p)


def test_per_site_interval(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "interval_seconds: 30\n"
        "sites:\n"
        "  - {name: a, url: 'https://a.example'}\n"
        "  - {name: demo, url: 'http://demo:8080', interval_seconds: 10}\n"
    )
    config = load_config(p)
    assert config.sites[0].interval_seconds == 30
    assert config.sites[1].interval_seconds == 10
    assert config.sites[0].is_https
    assert not config.sites[1].is_https
