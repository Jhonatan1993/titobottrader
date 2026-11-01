import json
import threading
from datetime import datetime, timezone

import pytest

from execution import practice_balance_capture as capture
from execution import iqoption_adapter


@pytest.mark.parametrize("entries", [
    [],
    [{"type": 1, "amount": 100, "currency": "USD"}],
    [{"type": 4, "amount": 1, "currency": "USD"}, {"type": 4, "amount": 2, "currency": "USD"}],
    [{"type": 4, "amount": "NaN", "currency": "USD"}],
    [{"type": 4, "amount": -1, "currency": "USD"}],
    [{"type": 4, "amount": True, "currency": "USD"}],
    [{"type": 4, "amount": 1, "currency": "usd"}],
    [{"type": 4, "amount": 1}],
])
def test_rejects_invalid_or_ambiguous_balances(entries):
    assert capture.parse_practice_profile({"balances": entries}) is None


def test_parse_only_practice_and_preserve_timestamp():
    when = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)
    profile = {"balances": [
        {"type": 1, "amount": 900, "currency": "COP"},
        {"type": 4, "amount": 0, "currency": "USD", "ssid": "secret"},
    ]}
    assert capture.parse_practice_profile(profile, now=when) == {
        "account": "PRACTICE", "amount": "0", "currency": "USD",
        "observed_at": "2026-10-31T17:00:00+00:00",
    }


def test_disabled_without_explicit_destination(monkeypatch, tmp_path):
    monkeypatch.delenv("IQOPTION_DEMO_BALANCE_CAPTURE_PATH", raising=False)
    assert capture.capture_practice_balance({"balances": [{"type": 4, "amount": 10, "currency": "USD"}]}) is False
    assert list(tmp_path.iterdir()) == []


def test_async_capture_is_atomic_and_excludes_secrets(tmp_path):
    destination = tmp_path / "balance.json"
    profile = {"balances": [{"type": 4, "amount": 10.25, "currency": "USD", "ssid": "secret"}]}
    assert capture.capture_practice_balance(profile, destination=destination)
    assert capture._write_lock.acquire(timeout=5)
    capture._write_lock.release()
    data = json.loads(destination.read_text())
    assert data["account"] == "PRACTICE"
    assert data["amount"] == "10.25"
    assert data["currency"] == "USD"
    assert "secret" not in destination.read_text()
    assert destination.stat().st_mode & 0o777 == 0o600


def test_busy_worker_does_not_block(tmp_path):
    assert capture._write_lock.acquire(blocking=False)
    try:
        assert not capture.capture_practice_balance(
            {"balances": [{"type": 4, "amount": 10, "currency": "USD"}]},
            destination=tmp_path / "balance.json",
        )
    finally:
        capture._write_lock.release()


def test_capture_disk_failure_releases_lock(tmp_path):
    assert capture.capture_practice_balance(
        {"balances": [{"type": 4, "amount": 10, "currency": "USD"}]},
        destination=tmp_path / "missing" / "balance.json",
    )
    assert capture._write_lock.acquire(timeout=5)
    capture._write_lock.release()


def test_adapter_profile_reaches_telegram_alert_without_extra_connection(monkeypatch, tmp_path):
    import websocket
    from scripts import practice_balance_copy
    from scripts import telegram_readonly_monitor

    source = tmp_path / "captured.json"
    copied = tmp_path / "copied.json"
    monkeypatch.setenv("IQOPTION_DEMO_BALANCE_CAPTURE_PATH", str(source))
    frames = iter([
        json.dumps({"name": "profile", "msg": {"balances": [
            {"type": 1, "id": 999, "amount": 5000, "currency": "USD"},
            {"type": 4, "id": 123, "amount": "42.50", "currency": "USD"},
        ]}}),
        json.dumps({"name": "positions", "msg": {"positions": []}}),
    ])

    class FakeSocket:
        def __init__(self):
            self.sent = []

        def send(self, message):
            self.sent.append(json.loads(message))

        def recv(self):
            return next(frames)

        def close(self):
            pass

    socket = FakeSocket()
    connections = []
    monkeypatch.setattr(
        websocket, "create_connection",
        lambda *args, **kwargs: connections.append(1) or socket,
    )
    adapter = iqoption_adapter.IQOptionAdapter(ssid="fake-session")
    assert adapter._fetch_live_balances_ws() is True
    assert capture._write_lock.acquire(timeout=5)
    capture._write_lock.release()
    assert len(connections) == 1
    assert not any(
        "open-option" in json.dumps(frame) or "place-market-order" in json.dumps(frame)
        for frame in socket.sent
    )
    assert practice_balance_copy.publish_copy(source, copied)
    reading = telegram_readonly_monitor.read_demo_balance(copied)
    assert reading is not None
    alert = telegram_readonly_monitor.format_trade_alert(
        {"id": "123", "result": "GANANCIA"}, reading
    )
    assert "42.50 USD" in alert
    assert "Bogotá" in alert
    assert "fake-session" not in source.read_text()
    assert "5000" not in copied.read_text()


def test_capture_failure_does_not_break_adapter(monkeypatch):
    import websocket

    frames = iter([
        json.dumps({"name": "profile", "msg": {"balances": [
            {"type": 4, "id": 123, "amount": 25, "currency": "USD"},
        ]}}),
        json.dumps({"name": "positions", "msg": {"positions": []}}),
    ])

    class FakeSocket:
        def send(self, message):
            pass

        def recv(self):
            return next(frames)

        def close(self):
            pass

    def broken_capture(profile):
        raise RuntimeError("simulated disk failure")

    monkeypatch.setattr(websocket, "create_connection", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr(iqoption_adapter, "capture_practice_balance", broken_capture)
    adapter = iqoption_adapter.IQOptionAdapter(ssid="fake-session")
    assert adapter._fetch_live_balances_ws() is True
    assert adapter.practice_amount == 25
    assert adapter.practice_balance_id == 123
