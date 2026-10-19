from remediation.docker_ops import DemoApp


def make(tmp_path, history):
    import json

    f = tmp_path / "deployments.json"
    f.write_text(json.dumps(history))
    return DemoApp(state_file=f, client=object())  # no real docker needed for this


def test_previous_good_version(tmp_path):
    demo = make(
        tmp_path,
        [
            {"version": "1.0", "ts": 1},
            {"version": "1.1", "ts": 2},
            {"version": "1.2-bad", "ts": 3},
        ],
    )
    assert demo.current_version() == "1.2-bad"
    assert demo.previous_good_version() == "1.1"


def test_skips_versions_marked_bad(tmp_path):
    demo = make(
        tmp_path,
        [
            {"version": "1.0", "ts": 1},
            {"version": "1.1", "ts": 2, "bad": True},
            {"version": "1.2", "ts": 3},
        ],
    )
    assert demo.previous_good_version() == "1.0"


def test_no_history(tmp_path):
    demo = DemoApp(state_file=tmp_path / "nope.json", client=object())
    assert demo.current_version() is None
    assert demo.previous_good_version() is None
