import json
from datetime import datetime, timedelta, timezone

import pytest

from execution import practice_balance_capture as capture
from scripts import practice_balance_copy as copy
from scripts import telegram_readonly_monitor as monitor


def test_capture_copy_and_alert_end_to_end(tmp_path):
    now = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)
    source = tmp_path / "source.json"
    destination = tmp_path / "balance.json"
    profile = {"balances": [
        {"type": 1, "amount": "999", "currency": "COP"},
        {"type": 4, "amount": "42.50", "currency": "USD", "ssid": "fake-secret"},
    ]}
    assert capture.capture_practice_balance(profile, destination=source, now=now)
    assert capture._write_lock.acquire(timeout=5)
    capture._write_lock.release()
    assert copy.publish_copy(source, destination, now=now + timedelta(seconds=5))
    data = json.loads(destination.read_text(encoding="utf-8"))
    assert set(data) == {"account", "amount", "currency", "observed_at"}
    assert "fake-secret" not in destination.read_text(encoding="utf-8")
    reading = monitor.read_demo_balance(destination, now=now + timedelta(seconds=10))
    alert = monitor.format_trade_alert({"id": "42", "result": "GANANCIA"}, reading)
    assert "42.50 USD" in alert
    assert "2026-10-31 12:00:00" in alert


@pytest.mark.parametrize("change", [
    {"account": "REAL"},
    {"amount": "NaN"},
    {"amount": "-1"},
    {"currency": "usd"},
    {"observed_at": "2026-10-31T16:57:00+00:00"},
    {"observed_at": "2026-10-31T17:00:00"},
])
def test_invalid_or_stale_source_publishes_unavailable(tmp_path, change):
    now = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)
    data = {
        "account": "PRACTICE", "amount": "42", "currency": "USD",
        "observed_at": now.isoformat(),
    }
    data.update(change)
    source = tmp_path / "source.json"
    destination = tmp_path / "balance.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    assert copy.publish_copy(source, destination, now=now) is False
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "account": "PRACTICE", "status": "unavailable",
    }
    assert monitor.read_demo_balance(destination, now=now) is None


def test_missing_source_does_not_reuse_old_copy(tmp_path):
    destination = tmp_path / "balance.json"
    destination.write_text('{"amount":"old"}', encoding="utf-8")
    assert copy.publish_copy(tmp_path / "missing", destination) is False
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "unavailable"
