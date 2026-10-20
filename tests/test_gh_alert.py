from statuspage.alert import state_change


def rows(*ups):
    return [{"up": u} for u in ups]


def test_one_failure_is_not_an_alert():
    assert state_change(rows(True, True, False)) is None


def test_two_failures_is_down():
    assert state_change(rows(True, True, False, False)) == "down"


def test_down_is_sent_only_once():
    assert state_change(rows(True, False, False, False)) is None


def test_recovered():
    assert state_change(rows(True, False, False, True)) == "recovered"


def test_recovered_after_one_failure_is_nothing():
    # we never sent DOWN for a single failure, so no RECOVERED either
    assert state_change(rows(True, False, True)) is None


def test_inconclusive_probes_are_skipped():
    assert state_change(rows(True, False, None, False)) == "down"


def test_not_enough_data():
    assert state_change(rows(False, False)) is None
