from unittest.mock import MagicMock

import pytest

from execution import trading_engine as module


@pytest.mark.parametrize("start_paused", [True, False])
def test_start_pause_controls_first_cycle(monkeypatch, start_paused):
    monkeypatch.setenv("TITOBOT_START_PAUSED", "true" if start_paused else "false")
    monkeypatch.setattr(module, "load_broker_config", lambda: {
        "iq_mode": "FOREX_CFD",
        "iqoption_environment": "PAPER",
        "profit_target_enabled": False,
        "max_loss_enabled": False,
    })
    feed = MagicMock()
    feed.iqoption.is_configured = False
    feed.tick.return_value = {}
    monkeypatch.setattr(module, "MultiAssetMarketFeed", lambda: feed)
    agent = MagicMock()
    monkeypatch.setattr(module, "IntelligentTradingAgent", lambda: agent)
    monkeypatch.setattr(module, "TradeJournal", MagicMock)
    risk = MagicMock()
    risk.snapshot.return_value = {"halted": False, "halted_reason": None}
    monkeypatch.setattr(module, "IQOptionRiskPolicy", lambda **kwargs: risk)
    monkeypatch.setattr(module, "RiskManager", MagicMock)
    binary = MagicMock()
    binary.has_active_position = False
    monkeypatch.setattr(module, "BinaryOptionsStrategyEngine", lambda **kwargs: binary)
    monkeypatch.setattr(module.RealTimeTradingEngine, "_record_equity_snapshot", lambda self: None)

    engine = module.RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    engine._evaluate_and_trade = MagicMock()

    assert engine.is_running is not start_paused
    assert engine.broker_wallets["IQOPTION"]["is_running"] is not start_paused
    engine.step()

    if start_paused:
        engine._evaluate_and_trade.assert_not_called()
    else:
        engine._evaluate_and_trade.assert_called_once()
