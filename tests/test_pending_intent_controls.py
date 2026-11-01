from types import SimpleNamespace
from unittest.mock import Mock

from execution.trading_engine import RealTimeTradingEngine
from risk_management.iqoption_risk_policy import IQOptionRiskPolicy


def make_engine(policy, active):
    engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
    engine.iq_mode = "BINARY_OPTIONS"
    engine.operating_mode = "IQ_BINARY"
    engine.execution_environment = "PAPER"
    engine.active_broker = "IQOPTION"
    engine.open_positions = {}
    engine._iqoption_order_pending = False
    engine.iqoption_risk_policy = policy
    engine.binary_engine = SimpleNamespace(has_active_position=active)
    engine.broker_wallets = {"IQOPTION": {"environment": "PAPER", "is_running": True}}
    engine.feed = SimpleNamespace(iqoption=SimpleNamespace(get_open_positions=lambda: []))
    engine.agent = SimpleNamespace(_add_thought=Mock())
    engine.is_running = True
    return engine


def test_active_order_blocks_entries_without_pausing_wallet(tmp_path):
    policy = IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json"))
    assert policy.begin_binary_order()
    engine = make_engine(policy, active=True)

    engine._apply_iqoption_daily_halt()
    assert engine.broker_wallets["IQOPTION"]["is_running"] is True
    assert not engine._iqoption_can_open()
    assert not engine.set_iq_mode("FOREX_CFD")["success"]
    assert not engine.set_execution_environment("LIVE_REAL")["success"]
    assert engine.resume_trading() is False
    assert policy.snapshot()["reconciliation_required"] is False


def test_restored_pending_order_pauses_wallet_and_blocks_mode_changes(tmp_path):
    path = tmp_path / "risk.json"
    policy = IQOptionRiskPolicy(state_path=str(path))
    assert policy.begin_binary_order()
    restored = IQOptionRiskPolicy(state_path=str(path))
    engine = make_engine(restored, active=False)

    engine._apply_iqoption_daily_halt()
    assert engine.broker_wallets["IQOPTION"]["is_running"] is False
    assert not engine._iqoption_can_open()
    assert not engine.set_iq_mode("FOREX_CFD")["success"]
    assert not engine.set_execution_environment("LIVE_REAL")["success"]
    assert engine.resume_trading() is False
    assert restored.snapshot()["binary_order_pending"] is True


def test_pending_intent_blocks_credential_updates_before_side_effects(tmp_path, monkeypatch):
    from execution import trading_engine

    path = tmp_path / "risk.json"
    policy = IQOptionRiskPolicy(state_path=str(path))
    assert policy.begin_binary_order()
    engine = make_engine(IQOptionRiskPolicy(state_path=str(path)), active=False)
    save = Mock()
    monkeypatch.setattr(trading_engine, "save_broker_config", save)
    engine.feed.reload_credentials = Mock()

    result = engine.update_broker_keys(iqoption_email="test@example.invalid")
    assert result["success"] is False
    save.assert_not_called()
    engine.feed.reload_credentials.assert_not_called()
    assert engine.iqoption_risk_policy.snapshot()["binary_order_pending"] is True
