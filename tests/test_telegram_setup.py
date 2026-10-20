from remediation.telegram_setup import find_chat_ids, read_env, set_env_value


def test_find_chat_ids():
    updates = {
        "ok": True,
        "result": [
            {"update_id": 1, "message": {"chat": {"id": 12345, "first_name": "Test"}}},
            {"update_id": 2, "message": {"chat": {"id": 12345, "first_name": "Test"}}},
        ],
    }
    assert find_chat_ids(updates) == {"12345": "Test"}
    assert find_chat_ids({"ok": True, "result": []}) == {}


def test_set_env_value(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nTELEGRAM_BOT_TOKEN=abc\nTELEGRAM_CHAT_ID=\nGRAFANA_PORT=3001\n")
    set_env_value(f, "TELEGRAM_CHAT_ID", "999")
    env = read_env(f)
    assert env["TELEGRAM_CHAT_ID"] == "999"
    assert env["TELEGRAM_BOT_TOKEN"] == "abc"
    assert env["GRAFANA_PORT"] == "3001"
    assert "# comment" in f.read_text()
