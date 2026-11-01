import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from execution.binary_options_engine import BinaryOptionsStrategyEngine
from risk_management.iqoption_risk_policy import IQOptionRiskPolicy


def make_engine(policy, pnl=-2.0):
    engine = BinaryOptionsStrategyEngine.__new__(BinaryOptionsStrategyEngine)
    engine.iq = SimpleNamespace(
        environment="PAPER",
        get_binary_option_result=Mock(return_value={
            "verified": True,
            "result": "LOSS" if pnl < 0 else "WIN",
            "pnl": pnl,
        }),
    )
    engine.risk_policy = policy
    engine.open_position = {
        "id": "12345", "symbol": "EURUSD", "direction": "CALL",
        "amount": 2.0, "entry_price": 1.1, "payout": 0.87,
        "entry_timestamp": 1, "expiration_timestamp": 1,
    }
    engine.soros_manager = SimpleNamespace(
        register_trade_result=Mock(return_value={}),
        release_currency_exposure=Mock(),
    )
    engine.journal = None
    engine.learner = None
    engine.telegram = SimpleNamespace(notify_result=Mock())
    engine.total_wins = engine.total_losses = engine.total_ties = 0
    engine.net_profit = 0.0
    engine.cooldown_duration = 120
    engine.last_trade_time = {}
    engine.asset_cooldown_until = {}
    engine.global_cooldown_until = 0
    return engine


@pytest.mark.parametrize("method", ["check_and_resolve_positions", "check_and_resolve_active_trade"])
def test_all_binary_settlement_paths_account_once(method, tmp_path):
    path = tmp_path / "risk.json"
    policy = IQOptionRiskPolicy(max_loss_amount=2, state_path=str(path))
    engine = make_engine(policy)
    result = getattr(engine, method)({} if method == "check_and_resolve_positions" else None)
    assert result["pnl"] == -2
    assert engine.open_position is None
    assert policy.snapshot()["realized_pnl"] == -2
    assert policy.snapshot()["halted_reason"] == "LIMITE_PERDIDA_DIARIA_ALCANZADO"
    policy.record_closed_trade(-2, trade_id="12345")
    restored = IQOptionRiskPolicy(max_loss_amount=2, state_path=str(path))
    assert restored.snapshot()["realized_pnl"] == -2


def test_settlement_journal_uses_aware_utc_timestamps(tmp_path):
    import datetime

    policy = IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json"))
    engine = make_engine(policy)
    engine.journal = SimpleNamespace(record_trade=Mock())
    assert engine.check_and_resolve_positions({})["pnl"] == -2
    recorded = engine.journal.record_trade.call_args.args[0]
    for key in ("opened_at", "closed_at"):
        timestamp = datetime.datetime.fromisoformat(recorded[key])
        assert timestamp.utcoffset() == datetime.timedelta(0)
    assert policy.snapshot()["realized_pnl"] == -2


def test_failed_risk_write_keeps_position_and_blocks(monkeypatch, tmp_path):
    policy = IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json"))
    engine = make_engine(policy)
    def fail_replace(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr("risk_management.iqoption_risk_policy.os.replace", fail_replace)
    assert engine.check_and_resolve_positions({}) is None
    assert engine.open_position["reconciliation_required"] is True
    assert policy.snapshot()["persistence_error"] is True
    assert not policy.can_open(0).allowed
    engine.soros_manager.register_trade_result.assert_not_called()


def test_journal_failure_keeps_reconciliation_halt_after_restart(tmp_path):
    path = tmp_path / "risk.json"
    policy = IQOptionRiskPolicy(state_path=str(path))
    engine = make_engine(policy)
    engine.journal = SimpleNamespace(record_trade=Mock(side_effect=OSError("disk full")))

    assert engine.check_and_resolve_positions({}) is None
    assert engine.open_position["reconciliation_required"] is True
    assert policy.snapshot()["realized_pnl"] == -2
    assert policy.snapshot()["reconciliation_required"] is True
    assert engine.total_losses == 0
    assert engine.net_profit == 0
    engine.soros_manager.register_trade_result.assert_not_called()
    engine.soros_manager.release_currency_exposure.assert_not_called()

    restored = IQOptionRiskPolicy(state_path=str(path))
    assert restored.snapshot()["realized_pnl"] == -2
    assert restored.snapshot()["reconciliation_required"] is True
    assert not restored.can_open(0).allowed


def test_real_journal_write_failure_requires_reconciliation(tmp_path):
    from trade_journal.journal import TradeJournal

    policy = IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json"))
    engine = make_engine(policy)
    engine.journal = TradeJournal(storage_dir=str(tmp_path / "journal"))
    engine.journal.json_file = str(tmp_path)
    assert engine.check_and_resolve_positions({}) is None
    assert engine.open_position["reconciliation_required"] is True
    assert policy.snapshot()["reconciliation_required"] is True
    assert IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json")).snapshot()["reconciliation_required"] is True


def test_unknown_settlement_does_not_release_or_account(tmp_path):
    policy = IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json"))
    engine = make_engine(policy)
    engine.iq.get_binary_option_result.return_value = None
    assert engine.check_and_resolve_positions({}) is None
    assert engine.open_position["status"] == "AWAITING_BROKER_SETTLEMENT"
    assert policy.snapshot()["realized_pnl"] == 0


def test_ambiguous_submit_exception_is_not_retried():
    engine = BinaryOptionsStrategyEngine.__new__(BinaryOptionsStrategyEngine)
    submit = Mock(side_effect=TypeError("failure after send"))
    engine.iq = SimpleNamespace(get_payout=lambda symbol: 0.87, submit_binary_option=submit)
    engine.open_position = None
    engine.min_payout = 0.85
    engine.global_cooldown_until = 0
    engine.last_trade_time = {}
    engine.soros_manager = SimpleNamespace(
        can_open_trade=lambda: (True, ""),
        check_currency_exposure=lambda *args: True,
        calculate_stake=lambda amount: amount,
        register_currency_exposure=Mock(),
    )
    result = engine.execute_binary_option("EURUSD", "CALL", 2, entry_price=1.1)
    assert result["unknown"] is True
    assert submit.call_count == 1
    assert engine.open_position["reconciliation_required"] is True


@pytest.mark.parametrize("reply", [
    {"success": True, "broker_confirmed": True},
    {"success": True, "order_id": "12345"},
])
def test_ambiguous_success_retains_position_and_blocks_second_send(reply):
    engine = BinaryOptionsStrategyEngine.__new__(BinaryOptionsStrategyEngine)
    submit = Mock(return_value=reply)
    engine.iq = SimpleNamespace(get_payout=lambda symbol: 0.87, submit_binary_option=submit)
    engine.open_position = None
    engine.min_payout = 0.85
    engine.global_cooldown_until = 0
    engine.last_trade_time = {}
    engine.soros_manager = SimpleNamespace(
        can_open_trade=lambda: (True, ""),
        check_currency_exposure=lambda *args: True,
        calculate_stake=lambda amount: amount,
        register_currency_exposure=Mock(),
    )
    result = engine.execute_binary_option("EURUSD", "CALL", 2, entry_price=1.1)
    assert result["unknown"] is True
    assert engine.open_position["reconciliation_required"] is True
    assert not engine.execute_binary_option("EURUSD", "CALL", 2, entry_price=1.1)["success"]
    assert submit.call_count == 1


@pytest.mark.parametrize("environment, expected_pnl", [("PAPER", -2.0), ("LIVE_REAL", 3.0)])
def test_binary_history_restoration_isolated_by_environment(environment, expected_pnl):
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    engine = BinaryOptionsStrategyEngine.__new__(BinaryOptionsStrategyEngine)
    engine.iq = SimpleNamespace(environment=environment)
    engine.journal = SimpleNamespace(trades=[
        {"id": "p", "broker": "IQOPTION", "environment": "PAPER",
         "category": "BINARY_OPTIONS", "settlement_verified": True, "closed_at": now, "pnl": -2.0},
        {"id": "r", "broker": "IQOPTION", "environment": "LIVE_REAL",
         "category": "BINARY_OPTIONS", "settlement_verified": True, "closed_at": now, "pnl": 3.0},
    ])
    engine.soros_manager = SimpleNamespace()
    engine.cooldown_duration = 120
    engine._restore_daily_risk_state()
    assert engine.soros_manager.daily_pnl == expected_pnl


def test_full_order_lifecycle_persists_intent_and_clears_after_settlement(tmp_path):
    path = tmp_path / "risk.json"
    policy = IQOptionRiskPolicy(state_path=str(path))
    engine = make_engine(policy)
    engine.open_position = None
    engine.iq.get_payout = lambda _: 0.87

    def submit(**kwargs):
        restored = IQOptionRiskPolicy(state_path=str(path))
        assert restored.snapshot()["binary_order_pending"] is True
        return {"success": True, "broker_confirmed": True, "order_id": "12345"}

    engine.iq.submit_binary_option = Mock(side_effect=submit)
    engine.soros_manager.can_open_trade = lambda: (True, "")
    engine.soros_manager.check_currency_exposure = lambda *args: True
    engine.soros_manager.calculate_stake = lambda amount: amount
    engine.soros_manager.register_currency_exposure = Mock()
    engine.soros_manager.soros_step = 0
    engine.telegram.notify_entry = Mock()
    engine.min_payout = 0.85
    engine.journal = SimpleNamespace(record_trade=Mock())

    result = engine.execute_binary_option("EURUSD", "CALL", 2, entry_price=1.1)
    assert result["success"] is True
    assert policy.snapshot()["binary_order_pending"] is True
    engine.open_position["expiration_timestamp"] = 0

    assert engine.check_and_resolve_positions({})["pnl"] == -2
    restored = IQOptionRiskPolicy(state_path=str(path))
    assert restored.snapshot()["binary_order_pending"] is False
    assert restored.snapshot()["realized_pnl"] == -2


@pytest.mark.parametrize("reply, pending", [
    ({"success": False, "order_not_sent": True, "error": "disconnected"}, False),
    ({"success": False, "error": "unknown"}, True),
])
def test_failed_submit_only_releases_explicit_unsent_intent(tmp_path, reply, pending):
    path = tmp_path / "risk.json"
    policy = IQOptionRiskPolicy(state_path=str(path))
    engine = make_engine(policy)
    engine.open_position = None
    engine.iq.get_payout = lambda _: 0.87
    engine.iq.submit_binary_option = Mock(return_value=reply)
    engine.soros_manager.can_open_trade = lambda: (True, "")
    engine.soros_manager.check_currency_exposure = lambda *args: True
    engine.soros_manager.calculate_stake = lambda amount: amount
    engine.soros_manager.register_currency_exposure = Mock()
    engine.min_payout = 0.85

    result = engine.execute_binary_option("EURUSD", "CALL", 2, entry_price=1.1)
    assert result["success"] is False
    assert IQOptionRiskPolicy(state_path=str(path)).snapshot()["binary_order_pending"] is pending
    assert (engine.open_position is not None) is pending
    if pending:
        assert result["unknown"] is True


def test_pending_order_blocks_after_restart_and_day_rollover(tmp_path, monkeypatch):
    path = tmp_path / "risk.json"
    monkeypatch.setattr(IQOptionRiskPolicy, "_today", staticmethod(lambda: "2026-01-01"))
    policy = IQOptionRiskPolicy(state_path=str(path))
    assert policy.begin_binary_order()
    assert policy.snapshot()["binary_order_pending"] is True

    monkeypatch.setattr(IQOptionRiskPolicy, "_today", staticmethod(lambda: "2026-01-02"))
    restored = IQOptionRiskPolicy(state_path=str(path))
    assert restored.snapshot()["binary_order_pending"] is True
    assert not restored.can_open(0).allowed
    assert not restored.begin_binary_order()


def test_pending_order_write_failure_prevents_adapter_call(tmp_path, monkeypatch):
    policy = IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json"))
    engine = BinaryOptionsStrategyEngine.__new__(BinaryOptionsStrategyEngine)
    submit = Mock()
    engine.iq = SimpleNamespace(get_payout=lambda _: 0.87, submit_binary_option=submit)
    engine.risk_policy = policy
    engine.open_position = None
    engine.min_payout = 0.85
    engine.global_cooldown_until = 0
    engine.last_trade_time = {}
    engine.soros_manager = SimpleNamespace(
        can_open_trade=lambda: (True, ""),
        check_currency_exposure=lambda *args: True,
        calculate_stake=lambda amount: amount,
    )

    def fail_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("risk_management.iqoption_risk_policy.os.replace", fail_replace)
    result = engine.execute_binary_option("EURUSD", "CALL", 2, entry_price=1.1)
    assert result["execution_blocked"] is True
    submit.assert_not_called()
    assert policy.snapshot()["persistence_error"] is True


def test_fsync_failure_before_send_preserves_previous_state(tmp_path, monkeypatch):
    path = tmp_path / "risk.json"
    policy = IQOptionRiskPolicy(state_path=str(path))
    previous = path.read_bytes()
    engine = BinaryOptionsStrategyEngine.__new__(BinaryOptionsStrategyEngine)
    submit = Mock()
    engine.iq = SimpleNamespace(get_payout=lambda _: 0.87, submit_binary_option=submit)
    engine.risk_policy = policy
    engine.open_position = None
    engine.min_payout = 0.85
    engine.global_cooldown_until = 0
    engine.last_trade_time = {}
    engine.soros_manager = SimpleNamespace(
        can_open_trade=lambda: (True, ""),
        check_currency_exposure=lambda *args: True,
        calculate_stake=lambda amount: amount,
    )

    def fail_fsync(fd):
        raise OSError("simulated sync failure")

    monkeypatch.setattr("risk_management.iqoption_risk_policy.os.fsync", fail_fsync)
    result = engine.execute_binary_option("EURUSD", "CALL", 2, entry_price=1.1)
    assert result["execution_blocked"] is True
    submit.assert_not_called()
    assert policy.snapshot()["persistence_error"] is True
    assert path.read_bytes() == previous
    assert list(tmp_path.glob(".risk-*")) == []


def test_reconciliation_survives_restart_on_new_utc_day(tmp_path, monkeypatch):
    path = tmp_path / "risk.json"
    path.write_text(json.dumps({
        "date_utc": "2026-01-01", "realized_pnl": -5,
        "closed_trade_ids": ["123"], "reconciliation_required": True,
    }))
    monkeypatch.setattr(IQOptionRiskPolicy, "_today", staticmethod(lambda: "2026-01-02"))
    restored = IQOptionRiskPolicy(state_path=str(path))
    assert restored.snapshot()["realized_pnl"] == 0
    assert restored.snapshot()["reconciliation_required"] is True
    assert not restored.can_open(0).allowed
    assert json.loads(path.read_text())["reconciliation_required"] is True
