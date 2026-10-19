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
