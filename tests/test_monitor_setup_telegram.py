import builtins
import stat

from monitoring import setup_telegram as setup


def prepare(monkeypatch, tmp_path, answers, responses):
    config = tmp_path / "telegram.env"
    calls = []
    monkeypatch.setattr(setup, "CONFIG", config)
    monkeypatch.setattr(setup.os, "geteuid", lambda: 0)
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(setup.getpass, "getpass", lambda _: "123:fake_token")
    values = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda _: next(values))

    def api(token, method, payload=None):
        calls.append((token, method, payload))
        result = responses[method]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(setup, "api", api)
    return config, calls


def test_setup_sends_test_and_writes_private_config(monkeypatch, tmp_path):
    responses = {
        "getWebhookInfo": {"url": ""},
        "getUpdates": [{"message": {"text": "/start", "chat": {
            "id": 42, "type": "private", "first_name": "Demo",
        }}}],
        "sendMessage": {"message_id": 1},
    }
    config, calls = prepare(monkeypatch, tmp_path, ["1", "s"], responses)
    assert setup.main() == 0
    assert config.read_text() == "TELEGRAM_BOT_TOKEN=123:fake_token\nTELEGRAM_CHAT_ID=42\n"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert [call[1] for call in calls] == ["getWebhookInfo", "getUpdates", "sendMessage"]
    assert calls[-1][2]["chat_id"] == 42


def test_setup_does_not_save_when_test_fails(monkeypatch, tmp_path):
    responses = {
        "getWebhookInfo": {"url": ""},
        "getUpdates": [{"message": {"text": "/start", "chat": {"id": 42, "type": "private"}}}],
        "sendMessage": OSError("fake-token must not appear"),
    }
    config, _ = prepare(monkeypatch, tmp_path, ["1", "s"], responses)
    assert setup.main() == 1
    assert not config.exists()


def test_setup_rejects_webhook_and_existing_configuration(monkeypatch, tmp_path):
    config, calls = prepare(monkeypatch, tmp_path, [], {"getWebhookInfo": {"url": "https://example.com"}})
    assert setup.main() == 1
    assert not config.exists()
    assert [call[1] for call in calls] == ["getWebhookInfo"]
    config.write_text("keep", encoding="utf-8")
    assert setup.main() == 1
    assert config.read_text(encoding="utf-8") == "keep"
