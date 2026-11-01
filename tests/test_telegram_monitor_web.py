import re
import sqlite3

import pytest
from werkzeug.security import generate_password_hash
from flask import Flask, g

from dashboard import telegram_monitor_config as config
from dashboard import telegram_monitor_web as web

REAL_REAUTHENTICATE = web._reauthenticate


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__, template_folder="../dashboard/templates")
    app.secret_key = "test-only-session-key"
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=True)
    app.register_blueprint(web.telegram_monitor_web)

    @app.before_request
    def set_user():
        g.current_user = app.config.get("TEST_USER")

    monkeypatch.setattr(web, "_reauthenticate", lambda user, password: password == "correct")
    return app


def test_admin_https_and_csrf_required(app, monkeypatch):
    client = app.test_client()
    app.config["TEST_USER"] = {"id": 1, "username": "admin", "role": "user", "status": "active"}
    assert client.get("/admin/telegram", base_url="https://example.test").status_code == 403
    app.config["TEST_USER"]["role"] = "admin"
    assert client.get("/admin/telegram", base_url="http://example.test").status_code == 403
    app.config["SESSION_COOKIE_SECURE"] = False
    assert client.get("/admin/telegram", base_url="https://example.test").status_code == 403
    app.config["SESSION_COOKIE_SECURE"] = True
    page = client.get("/admin/telegram", base_url="https://example.test")
    assert page.status_code == 200
    csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    called = []
    monkeypatch.setattr(web.config, "discover_chats", lambda token: called.append(token) or {"bot": "demo", "chats": []})
    payload = {"token": "123:example", "password": "correct"}
    url = "/api/admin/telegram-monitor/discover"
    assert client.post(url, base_url="https://example.test", json=payload).status_code == 403
    assert client.post(url, base_url="https://example.test", json=payload,
                       headers={"Origin": "https://evil.test", "X-CSRF-Token": csrf}).status_code == 403
    assert not called
    assert client.post(url, base_url="https://example.test", json=payload,
                       headers={"Origin": "https://example.test", "X-CSRF-Token": csrf}).status_code == 200
    assert called == ["123:example"]


def test_password_required_to_configure(app, monkeypatch):
    app.config["TEST_USER"] = {"id": 1, "username": "admin", "role": "admin", "status": "active"}
    client = app.test_client()
    page = client.get("/admin/telegram", base_url="https://example.test")
    csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    calls = []
    monkeypatch.setattr(web.config, "configure", lambda *args: calls.append(args))
    response = client.post(
        "/api/admin/telegram-monitor/configure", base_url="https://example.test",
        json={"token": "123:example", "chat_id": "42", "password": "wrong"},
        headers={"Origin": "https://example.test", "X-CSRF-Token": csrf},
    )
    assert response.status_code == 403
    assert not calls
    assert b"123:example" not in response.data


def test_real_password_verification_with_temporary_database(app, monkeypatch, tmp_path):
    from dashboard import auth_manager

    database = tmp_path / "users.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, "
            "role TEXT, status TEXT, last_login TEXT)"
        )
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (1, "test-admin", generate_password_hash("correct-password"), "admin", "active", ""),
        )
    monkeypatch.setattr(auth_manager, "DB_PATH", str(database))
    monkeypatch.setattr(auth_manager, "get_database_url", lambda: "")
    monkeypatch.setattr(web, "_reauthenticate", REAL_REAUTHENTICATE)
    monkeypatch.setattr(web, "RATE_LIMITER", web.RATE_LIMITER.__class__())
    calls = []
    monkeypatch.setattr(web.config, "discover_chats", lambda token: calls.append(token) or {"bot": "demo", "chats": []})
    app.config["TEST_USER"] = {"id": 1, "username": "test-admin", "role": "admin", "status": "active"}
    client = app.test_client()
    page = client.get("/admin/telegram", base_url="https://example.test")
    csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    headers = {"Origin": "https://example.test", "X-CSRF-Token": csrf}
    url = "/api/admin/telegram-monitor/discover"
    denied = client.post(url, base_url="https://example.test",
                         json={"token": "123:example", "password": "incorrect"}, headers=headers)
    assert denied.status_code == 403
    assert calls == []
    allowed = client.post(url, base_url="https://example.test",
                          json={"token": "123:example", "password": "correct-password"}, headers=headers)
    assert allowed.status_code == 200
    assert calls == ["123:example"]
    assert b"123:example" not in allowed.data


def test_telegram_redirect_is_rejected_without_exposing_token():
    with pytest.raises(config.ConfigurationError) as error:
        config.RejectRedirects().redirect_request(None, None, 302, "", {}, "https://example.test/")
    assert "123:example" not in str(error.value)


def test_telegram_transport_error_does_not_expose_token(monkeypatch):
    class FailingOpener:
        def open(self, request, timeout):
            raise OSError(request.full_url)

    monkeypatch.setattr(config, "build_opener", lambda *handlers: FailingOpener())
    with pytest.raises(config.ConfigurationError) as error:
        config.telegram_call("123:example", "getMe")
    assert "123:example" not in str(error.value)


@pytest.mark.parametrize(
    "states,should_fail",
    [
        (["ActiveState=active\nMainPID=123\n", "ActiveState=active\nMainPID=123\n"], False),
        (["ActiveState=active\nMainPID=123\n", "ActiveState=failed\nMainPID=0\n"], True),
        (["ActiveState=active\nMainPID=123\n", "ActiveState=active\nMainPID=456\n"], True),
    ],
)
def test_restart_monitor_checks_stable_process(monkeypatch, states, should_fail):
    responses = iter(states)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return type("Result", (), {"stdout": next(responses) if command[1] == "show" else ""})()

    monkeypatch.setattr(config.subprocess, "run", fake_run)
    monkeypatch.setattr(config.time, "sleep", lambda _: None)
    if should_fail:
        with pytest.raises(config.ConfigurationError):
            config.restart_monitor()
    else:
        config.restart_monitor()
    assert calls[0] == ["systemctl", "restart", config.SERVICE]


def test_telegram_failure_preserves_existing_config(tmp_path):
    path = tmp_path / "telegram.env"
    path.write_bytes(b"previous configuration")
    calls = []

    def api(token, method, payload):
        calls.append(method)
        if method == "getChat":
            return {"type": "private", "id": 42}
        raise config.ConfigurationError("Telegram no disponible")

    with pytest.raises(config.ConfigurationError):
        config.configure("123:example", "42", path, tmp_path / "lock", api, lambda: None)
    assert path.read_bytes() == b"previous configuration"
    assert calls == ["getChat", "sendMessage"]


def test_restart_failure_restores_previous_config(tmp_path):
    path = tmp_path / "telegram.env"
    path.write_bytes(b"previous configuration")
    calls = []

    def api(token, method, payload):
        if method == "getChat":
            return {"type": "private", "id": 42}
        return {"message_id": 1}

    def restart():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("failed")

    with pytest.raises(config.ConfigurationError, match="restauró"):
        config.configure("123:example", "42", path, tmp_path / "lock", api, restart)
    assert path.read_bytes() == b"previous configuration"
    assert len(calls) == 2
    assert path.stat().st_mode & 0o777 == 0o600


def test_rejects_group_without_sending_or_modifying_config(tmp_path):
    path = tmp_path / "telegram.env"
    path.write_bytes(b"previous configuration")
    calls = []

    def api(token, method, payload):
        calls.append(method)
        return {"type": "group", "id": 42}

    with pytest.raises(config.ConfigurationError, match="chat privado"):
        config.configure("123:example", "42", path, tmp_path / "lock", api, lambda: calls.append("restart"))
    assert calls == ["getChat"]
    assert path.read_bytes() == b"previous configuration"


def test_restart_failure_without_previous_config_removes_new_config(tmp_path):
    path = tmp_path / "telegram.env"

    def api(token, method, payload):
        if method == "getChat":
            return {"type": "private", "id": 42}
        return {"message_id": 1}

    def restart():
        raise RuntimeError("failed")

    with pytest.raises(config.ConfigurationError, match="se retiró la configuración nueva"):
        config.configure("123:example", "42", path, tmp_path / "lock", api, restart)
    assert not path.exists()


def test_success_writes_private_config_after_test(tmp_path):
    path = tmp_path / "telegram.env"
    calls = []

    def api(token, method, payload):
        calls.append(method)
        if method == "getChat":
            return {"type": "private", "id": 42}
        return {"message_id": 1}

    config.configure("123:example", "42", path, tmp_path / "lock", api, lambda: calls.append("restart"))
    assert calls == ["getChat", "sendMessage", "restart"]
    assert path.read_bytes() == b"TELEGRAM_BOT_TOKEN=123:example\nTELEGRAM_CHAT_ID=42\n"
    assert path.stat().st_mode & 0o777 == 0o600
