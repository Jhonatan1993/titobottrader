import json

import pytest

from scripts import demo_balance_snapshot as balance


def profile(entries):
    return {"name": "profile", "msg": {"balances": entries}}


@pytest.mark.parametrize("entries", [
    [],
    [{"type": 1, "amount": 123, "currency": "USD"}],
    [{"type": 4, "amount": 1, "currency": "USD"}, {"type": 4, "amount": 2, "currency": "USD"}],
    [{"type": 4, "amount": "NaN", "currency": "USD"}],
    [{"type": 4, "amount": -1, "currency": "USD"}],
    [{"type": 4, "amount": True, "currency": "USD"}],
    [{"type": 4, "amount": 1, "currency": "usd"}],
    [{"type": 4, "amount": 1}],
])
def test_invalid_profiles_are_rejected(entries):
    assert balance.parse_demo_profile(profile(entries)) is None


def test_demo_balance_including_zero_is_recognized():
    result = balance.parse_demo_profile(profile([
        {"type": 1, "amount": 100, "currency": "COP"},
        {"type": 4, "amount": 0, "currency": "USD"},
    ]))
    assert result == {"account": "PRACTICE", "amount": "0", "currency": "USD"}


def test_query_only_authenticates_and_closes_connection():
    class FakeSocket:
        def __init__(self):
            self.sent = []
            self.closed = False

        def send(self, data):
            self.sent.append(json.loads(data))

        def recv(self):
            return json.dumps(profile([{"type": 4, "amount": 10.25, "currency": "USD"}]))

        def close(self):
            self.closed = True

    ws = FakeSocket()
    connection_options = {}

    def connect(url, **kwargs):
        connection_options.update(kwargs)
        return ws

    result = balance.query_demo_balance("fake-session", connect=connect)
    assert [message["name"] for message in ws.sent] == ["authenticate", "ssid"]
    assert result["amount"] == "10.25"
    assert result["account"] == "PRACTICE"
    assert result["observed_at"].endswith("+00:00")
    assert connection_options["sslopt"]["check_hostname"] is True
    assert ws.closed


def test_retry_only_for_missing_profile():
    attempts = []
    waits = []

    def missing_then_success(ssid, *, timeout):
        attempts.append((ssid, timeout))
        if len(attempts) == 1:
            raise balance.BalanceReadError("PERFIL_NO_RECIBIDO")
        return {"account": "PRACTICE", "amount": "10", "currency": "USD"}

    assert balance.query_with_retry("fake-session", query=missing_then_success, sleep=waits.append)["amount"] == "10"
    assert attempts == [("fake-session", 8), ("fake-session", 8)]
    assert waits == [1]


def test_retry_stops_after_two_missing_profiles():
    attempts = []

    def missing(ssid, *, timeout):
        attempts.append(1)
        raise balance.BalanceReadError("PERFIL_NO_RECIBIDO")

    with pytest.raises(balance.BalanceReadError, match="PERFIL_NO_RECIBIDO"):
        balance.query_with_retry("fake-session", query=missing, sleep=lambda _: None)
    assert len(attempts) == 2


def test_invalid_profile_is_not_retried():
    attempts = []

    def invalid(ssid, *, timeout):
        attempts.append(1)
        raise balance.BalanceReadError("PERFIL_SIN_SALDO_DEMO_VALIDO")

    with pytest.raises(balance.BalanceReadError, match="PERFIL_SIN_SALDO_DEMO_VALIDO"):
        balance.query_with_retry("fake-session", query=invalid, sleep=lambda _: None)
    assert len(attempts) == 1


def test_failed_query_invalidates_previous_reading(monkeypatch, tmp_path, capsys):
    config = tmp_path / "broker.json"
    destination = tmp_path / "balance.json"
    config.write_text(json.dumps({"iqoption": {"ssid": "fake-secret"}}))
    destination.write_text(json.dumps({
        "account": "PRACTICE", "amount": "25", "currency": "USD",
        "observed_at": "2026-10-31T16:47:41+00:00",
    }))
    monkeypatch.setattr(
        balance, "query_demo_balance",
        lambda _ssid, **kwargs: (_ for _ in ()).throw(RuntimeError("fake-secret")),
    )
    monkeypatch.setattr(
        "sys.argv", ["balance", "--config", str(config), "--destination", str(destination)]
    )
    assert balance.main() == 1
    result = json.loads(destination.read_text())
    assert result["status"] == "unavailable"
    assert "amount" not in result
    assert "fake-secret" not in destination.read_text()
    assert "fake-secret" not in capsys.readouterr().out


def test_published_snapshot_excludes_credentials_and_real_account(tmp_path):
    path = tmp_path / "balance.json"
    reading = {"account": "PRACTICE", "amount": "10.25", "currency": "USD", "observed_at": "2026-10-31T16:47:41+00:00"}
    balance.publish_snapshot(path, reading)
    assert json.loads(path.read_text()) == reading
    assert path.stat().st_mode & 0o777 == 0o640
