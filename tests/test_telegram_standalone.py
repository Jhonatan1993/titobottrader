import re

import pytest
from flask import Flask

from dashboard import telegram_standalone as standalone


MAIN_KEY = "main-test-secret-" + "m" * 40
ADMIN_KEY = "telegram-test-secret-" + "t" * 40
ADMIN = {"id": 1, "username": "admin", "role": "admin", "status": "active"}
USER = {"id": 2, "username": "user", "role": "user", "status": "active"}


def signed_main_session(data, key=MAIN_KEY):
    main = Flask("test_main")
    main.secret_key = key
    serializer = main.session_interface.get_signing_serializer(main)
    return serializer.dumps(data)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        standalone, "get_user_by_id",
        lambda user_id: ADMIN if user_id == 1 else USER if user_id == 2 else None,
    )
    instance = standalone.create_app(ADMIN_KEY, MAIN_KEY)
    instance.config["TESTING"] = True
    return instance


def test_requires_long_independent_and_main_secrets():
    with pytest.raises(RuntimeError):
        standalone.create_app("short", MAIN_KEY)
    with pytest.raises(RuntimeError):
        standalone.create_app(ADMIN_KEY, "short")


def test_requires_https_and_signed_main_session(app):
    client = app.test_client()
    assert client.get("/admin/telegram", base_url="http://example.test").status_code == 403
    response = client.get("/admin/telegram", base_url="https://example.test")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert client.get("/api/admin/telegram-monitor/status", base_url="https://example.test").status_code == 401

    client.set_cookie("session", signed_main_session({"user_id": 1}, key="other" * 10), domain="example.test")
    assert client.get("/admin/telegram", base_url="https://example.test").headers["Location"] == "/login"

    client.set_cookie("session", "invalid", domain="example.test")
    assert client.get("/admin/telegram", base_url="https://example.test").headers["Location"] == "/login"


def test_admin_uses_main_session_without_second_login(app):
    client = app.test_client()
    main_cookie = signed_main_session({"user_id": 1, "username": "admin", "_permanent": True})
    client.set_cookie("session", main_cookie, domain="example.test")
    response = client.get("/admin/telegram", base_url="https://example.test")
    assert response.status_code == 200
    assert b"Token nuevo" in response.data
    cookies = response.headers.getlist("Set-Cookie")
    assert any("titobot_telegram_admin=" in c and "Secure" in c and "HttpOnly" in c for c in cookies)
    assert not any(c.startswith("session=") for c in cookies)
    assert client.get_cookie("session", domain="example.test").value == main_cookie


def test_user_or_revoked_admin_cannot_access(app, monkeypatch):
    client = app.test_client()
    client.set_cookie("session", signed_main_session({"user_id": 2}), domain="example.test")
    assert client.get("/admin/telegram", base_url="https://example.test").status_code == 403
    client.set_cookie("session", signed_main_session({"user_id": 1}), domain="example.test")
    assert client.get("/admin/telegram", base_url="https://example.test").status_code == 200
    monkeypatch.setattr(standalone, "get_user_by_id", lambda _: {**ADMIN, "status": "suspended"})
    assert client.get("/admin/telegram", base_url="https://example.test").status_code == 403


def test_removing_main_session_revokes_access_even_with_csrf_cookie(app):
    client = app.test_client()
    client.set_cookie("session", signed_main_session({"user_id": 1}), domain="example.test")
    assert client.get("/admin/telegram", base_url="https://example.test").status_code == 200
    client.delete_cookie("session", domain="example.test")
    response = client.get("/admin/telegram", base_url="https://example.test")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_api_requires_csrf_origin_and_password(app, monkeypatch):
    from dashboard import telegram_monitor_web as web

    client = app.test_client()
    client.set_cookie("session", signed_main_session({"user_id": 1}), domain="example.test")
    page = client.get("/admin/telegram", base_url="https://example.test")
    csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    calls = []
    monkeypatch.setattr(web, "_reauthenticate", lambda user, password: password == "correct")
    monkeypatch.setattr(web.config, "configure", lambda *args: calls.append(args))
    payload = {"token": "123:example", "chat_id": "42", "password": "wrong"}
    url = "/api/admin/telegram-monitor/configure"
    headers = {"Origin": "https://example.test", "X-CSRF-Token": csrf}
    assert client.post(url, base_url="https://example.test", json=payload).status_code == 403
    assert client.post(url, base_url="https://example.test", json=payload,
                       headers={"Origin": "https://evil.test", "X-CSRF-Token": csrf}).status_code == 403
    assert client.post(url, base_url="https://example.test", json=payload, headers=headers).status_code == 403
    assert calls == []
    payload["password"] = "correct"
    assert client.post(url, base_url="https://example.test", json=payload, headers=headers).status_code == 200
    assert calls == [("123:example", "42")]


def test_main_session_key_missing_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.setattr(standalone, "SECRET_FILE", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="unavailable"):
        standalone.create_app(ADMIN_KEY)
    assert not (tmp_path / "missing").exists()
