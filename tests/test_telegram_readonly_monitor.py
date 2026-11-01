import json
import os
import time
from datetime import datetime

import pytest

from scripts import monitor_snapshot, telegram_readonly_monitor as monitor


def trade(ident, **overrides):
    row = {
        "id": ident,
        "broker": "IQOPTION",
        "category": "BINARY_OPTIONS",
        "environment": "PAPER",
        "settlement_verified": True,
        "symbol": "EURUSD",
        "result": "GANANCIA",
        "pnl": 1.7,
        "closed_at": "2026-10-31 15:00:00",
    }
    row.update(overrides)
    return row


def write_history(path, rows):
    path.write_text(json.dumps(rows), encoding="utf-8")


def test_initial_history_is_baseline_and_new_demo_settlement_alerts_once(tmp_path):
    history = tmp_path / "history.json"
    write_history(history, [trade("old"), trade("real", environment="LIVE_REAL")])
    state = monitor.load_state(tmp_path / "state.json")

    monitor.check_once(state, history, lambda: "active")
    assert state["initialized"] is True
    assert state["seen"] == ["old"]
    assert not any("ID: old" in message for message in state["pending"])
    state["pending"].clear()

    write_history(history, [trade("new"), trade("new"), trade("old")])
    monitor.check_once(state, history, lambda: "active")
    assert sum("ID: new" in message for message in state["pending"]) == 1
    assert "no comprobada directamente" in state["pending"][0]
    state["pending"].clear()

    monitor.check_once(state, history, lambda: "active")
    assert state["pending"] == []


def test_history_error_alerts_once_and_recovers_without_losing_baseline(tmp_path):
    history = tmp_path / "history.json"
    state = monitor.load_state(tmp_path / "state.json")
    write_history(history, [trade("old")])
    monitor.check_once(state, history, lambda: "active")
    state["pending"].clear()

    history.write_text("{", encoding="utf-8")
    monitor.check_once(state, history, lambda: "active")
    monitor.check_once(state, history, lambda: "active")
    assert sum("historial inaccesible" in message for message in state["pending"]) == 1
    assert state["seen"] == ["old"]

    write_history(history, [trade("new"), trade("old")])
    monitor.check_once(state, history, lambda: "active")
    assert any("restablecida" in message for message in state["pending"])
    assert any("ID: new" in message for message in state["pending"])


def test_stale_snapshot_is_reported_and_recovers(tmp_path):
    history = tmp_path / "history.json"
    write_history(history, [trade("old")])
    state = monitor.load_state(tmp_path / "state.json")
    monitor.check_once(state, history, lambda: "active")
    state["pending"].clear()
    old = time.time() - 300
    os.utime(history, (old, old))
    monitor.check_once(state, history, lambda: "active")
    assert state["history_error"] is True
    assert any("desactualizado" in message for message in state["pending"])
    write_history(history, [trade("new"), trade("old")])
    monitor.check_once(state, history, lambda: "active")
    assert any("restablecida" in message for message in state["pending"])
    assert any("ID: new" in message for message in state["pending"])


@pytest.mark.parametrize(
    "outcome, header",
    [
        ("GANANCIA", "🟢 GANANCIA"),
        ("PÉRDIDA CONTROLADA", "🔴 PÉRDIDA"),
        ("EMPATE", "⚪ EMPATE"),
        ("desconocido", "⚠️ RESULTADO DESCONOCIDO"),
    ],
)
def test_trade_alert_distinguishes_outcomes_and_does_not_invent_balance(outcome, header):
    message = monitor.format_trade_alert(trade("123", result=outcome))
    assert message.startswith(header)
    assert "BINARIA DEMO" in message
    assert "Saldo Demo (última lectura): no disponible" in message
    assert "no comprobada directamente con IQ Option" in message
    assert "ID: 123" in message


@pytest.mark.parametrize(
    "changes",
    [
        {"account": "REAL"},
        {"amount": "NaN"},
        {"amount": "-1"},
        {"amount": True},
        {"currency": "usd"},
        {"observed_at": "2026-10-31T16:47:41"},
        {"observed_at": "2026-10-31T16:45:00+00:00"},
        {"observed_at": "2026-10-31T16:48:00+00:00"},
    ],
)
def test_invalid_or_stale_demo_balance_is_not_used(tmp_path, changes):
    path = tmp_path / "balance.json"
    snapshot = {
        "account": "PRACTICE",
        "amount": "11610.17",
        "currency": "USD",
        "observed_at": "2026-10-31T16:47:41+00:00",
    }
    snapshot.update(changes)
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    now = datetime.fromisoformat("2026-10-31T16:47:45+00:00")
    assert monitor.read_demo_balance(path, now=now) is None


@pytest.mark.parametrize("amount", ["11610.17", "0"])
def test_fresh_demo_balance_includes_amount_currency_and_time(tmp_path, amount):
    path = tmp_path / "balance.json"
    path.write_text(json.dumps({
        "account": "PRACTICE",
        "amount": amount,
        "currency": "USD",
        "observed_at": "2026-10-31T16:47:41+00:00",
    }), encoding="utf-8")
    now = datetime.fromisoformat("2026-10-31T16:47:45+00:00")
    balance = monitor.read_demo_balance(path, now=now)
    message = monitor.format_trade_alert(trade("123"), balance)
    assert f"{amount} USD" in message
    assert "2026-10-31 11:47:41" in message
    assert "última lectura" in message


def test_queued_alert_refreshes_balance_at_delivery(tmp_path):
    from decimal import Decimal
    path = tmp_path / "balance.json"
    reading = {
        "account": "PRACTICE", "amount": "12.50", "currency": "USD",
        "observed_at": "2026-10-31T16:47:41+00:00",
    }
    path.write_text(json.dumps(reading), encoding="utf-8")
    old_balance = {"amount": Decimal("999"), "currency": "USD",
                   "observed_at": datetime.fromisoformat("2026-10-31T16:40:00+00:00")}
    queued = monitor.format_trade_alert(trade("42"), old_balance)
    fresh = monitor.read_demo_balance(path, now=datetime.fromisoformat("2026-10-31T16:47:50+00:00"))
    delivered = monitor.refresh_queued_balance(queued, fresh)
    assert "12.50 USD" in delivered
    assert "999 USD" not in delivered
    stale = monitor.read_demo_balance(path, now=datetime.fromisoformat("2026-10-31T16:51:00+00:00"))
    delivered = monitor.refresh_queued_balance(queued, stale)
    assert "no disponible" in delivered
    assert "999 USD" not in delivered
    assert monitor.refresh_queued_balance("Servicio activo", fresh) == "Servicio activo"


def test_snapshot_filters_fields_and_preserves_previous_on_bad_json(tmp_path):
    source = tmp_path / "source.json"
    destination = tmp_path / "snapshot.json"
    write_history(source, [
        trade("demo", password="secret"),
        trade("real", environment="LIVE_REAL"),
    ])
    monitor_snapshot.make_snapshot(source, destination)
    assert json.loads(destination.read_text()) == [trade("demo")]
    assert destination.stat().st_mode & 0o777 == 0o640
    previous = destination.read_bytes()
    source.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        monitor_snapshot.make_snapshot(source, destination)
    assert destination.read_bytes() == previous
    with pytest.raises(ValueError):
        monitor_snapshot.make_snapshot(source, source)


def test_service_changes_alert_once(tmp_path):
    history = tmp_path / "history.json"
    write_history(history, [])
    state = monitor.load_state(tmp_path / "state.json")
    monitor.check_once(state, history, lambda: "active")
    state["pending"].clear()
    monitor.check_once(state, history, lambda: "failed")
    monitor.check_once(state, history, lambda: "failed")
    assert len(state["pending"]) == 1
    assert "servicio failed" in state["pending"][0]


def test_state_roundtrip_and_invalid_state(tmp_path):
    path = tmp_path / "private" / "state.json"
    state = monitor.load_state(path)
    state["pending"].append("pending")
    monitor.save_state(path, state)
    assert monitor.load_state(path) == state
    path.write_text('{"seen": "wrong", "pending": []}', encoding="utf-8")
    with pytest.raises(ValueError):
        monitor.load_state(path)


def test_daily_report_uses_bogota_date_and_is_queued_once(tmp_path):
    history = tmp_path / "history.json"
    write_history(history, [
        trade("today", closed_at="2026-11-01T04:50:00+00:00", pnl=1.7),
        trade("yesterday", closed_at="2026-10-31T04:50:00+00:00", pnl=-2),
        trade("invalid", closed_at="invalid", pnl=2),
    ])
    state = monitor.load_state(tmp_path / "state.json")
    now = datetime.fromisoformat("2026-10-31T23:55:00-05:00")

    monitor.check_once(state, history, lambda: "active", now=now)
    reports = [message for message in state["pending"] if message.startswith("Resumen")]
    assert len(reports) == 1
    assert "2026-10-31" in reports[0]
    assert "1 operaciones" in reports[0]
    assert "PnL=1.7" in reports[0]
    assert "inválidos excluidos: 1" in reports[0]
    assert "sin verificación directa" in reports[0]
    monitor.check_once(state, history, lambda: "active", now=now)
    assert sum(message.startswith("Resumen") for message in state["pending"]) == 1


def test_send_message_checks_telegram_response_without_network(monkeypatch):
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(monitor, "urlopen", fake_urlopen)
    monitor.send_message("fake-token", "fake-chat", "hello")
    request, timeout = requests[0]
    assert timeout == 10
    assert json.loads(request.data) == {"chat_id": "fake-chat", "text": "hello"}
