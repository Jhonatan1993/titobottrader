import io
import json
import stat

from monitoring import setup_visual_backend as backend


def setup_case(monkeypatch, tmp_path, request, selection=None, responses=None):
    config = tmp_path / "telegram.env"
    monkeypatch.setattr(backend, "CONFIG", config)
    monkeypatch.setattr(backend.os, "geteuid", lambda: 0)
    lines = [json.dumps(request)]
    if selection is not None:
        lines.append(json.dumps(selection))
    monkeypatch.setattr(backend.sys, "stdin", io.StringIO("\n".join(lines) + "\n"))
    calls = []

    def fake_api(token, method, payload=None):
        calls.append((method, payload))
        value = responses[method]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(backend, "api", fake_api)
    return config, calls


def test_visual_setup_sends_to_selected_private_chat(monkeypatch, tmp_path, capsys):
    responses = {
        "getMe": {"username": "TraderTitoBot"},
        "getWebhookInfo": {"url": ""},
        "getUpdates": [
            {"message": {"text": "hola", "chat": {"id": 42, "type": "private", "first_name": "Ana"}}},
            {"message": {"text": "/start", "chat": {"id": -7, "type": "group"}}},
        ],
        "sendMessage": {"message_id": 1},
    }
    config, calls = setup_case(monkeypatch, tmp_path, {"token": "123:fake-token"}, {"index": 0}, responses)
    assert backend.main() == 0
    output = capsys.readouterr().out
    assert "fake-token" not in output
    assert json.loads(output.splitlines()[0]) == {"bot": "TraderTitoBot", "chats": [{"index": 0, "name": "Ana"}]}
    assert json.loads(output.splitlines()[1])["success"] is True
    assert config.read_text() == "TELEGRAM_BOT_TOKEN=123:fake-token\nTELEGRAM_CHAT_ID=42\n"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert calls[-1][0] == "sendMessage"
    assert calls[-1][1]["chat_id"] == 42


def test_visual_setup_does_not_leak_or_save_on_api_error(monkeypatch, tmp_path, capsys):
    responses = {"getMe": OSError("123:fake-token")}
    config, _ = setup_case(monkeypatch, tmp_path, {"token": "123:fake-token"}, responses=responses)
    assert backend.main() == 1
    assert "fake-token" not in capsys.readouterr().out
    assert not config.exists()


def test_visual_setup_rejects_invalid_selection_and_existing_config(monkeypatch, tmp_path, capsys):
    responses = {
        "getMe": {"username": "TraderTitoBot"},
        "getWebhookInfo": {"url": ""},
        "getUpdates": [{"message": {"text": "/start", "chat": {"id": 42, "type": "private"}}}],
    }
    config, calls = setup_case(monkeypatch, tmp_path, {"token": "123:fake-token"}, {"index": 3}, responses)
    assert backend.main() == 1
    assert not config.exists()
    assert [call[0] for call in calls] == ["getMe", "getWebhookInfo", "getUpdates"]
    capsys.readouterr()

    config.write_text("existing")
    assert backend.main() == 1
    assert config.read_text() == "existing"


def test_visual_setup_reports_identified_bot_without_pending_chats(monkeypatch, tmp_path, capsys):
    responses = {
        "getMe": {"username": "TraderTitoBot"},
        "getWebhookInfo": {"url": ""},
        "getUpdates": [],
    }
    config, _ = setup_case(monkeypatch, tmp_path, {"token": "123:fake-token"}, responses=responses)
    assert backend.main() == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert "@TraderTitoBot" in error
    assert "fake-token" not in error
    assert not config.exists()
