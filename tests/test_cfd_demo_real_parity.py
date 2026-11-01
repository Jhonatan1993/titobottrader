from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from execution import trading_engine
from execution.trading_engine import RealTimeTradingEngine


@pytest.mark.parametrize("decision,confidence", [("BUY", 90), ("PUT", 87), ("HOLD", 40)])
def test_cfd_selection_is_shared_for_equal_inputs(decision, confidence, monkeypatch):
    monkeypatch.setattr(trading_engine.time, "time", lambda: 1800000000.0)
    market = {"EURUSD": {"symbol": "EURUSD", "category": "FOREX", "price": 1.05}}

    def run(environment):
        engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
        engine.active_broker = "IQOPTION"
        engine.iq_mode = "FOREX_CFD"
        engine.execution_environment = environment
        engine.open_positions = {}
        engine.broker_wallets = {"IQOPTION": {
            "environment": environment, "is_running": True, "cash": 10000,
            "allowed_categories": ["FOREX"],
        }}
        engine._broker_order_failure_cooldown = {}
        engine.last_exit_times = {}
        engine.get_broker_positions = lambda _: []
        engine.feed = SimpleNamespace(
            iqoption=SimpleNamespace(currency="USD"),
            get_verified_iq_market_snapshot=lambda _: {"current_price": 1.05},
            enrich_asset_from_iq_snapshot=lambda asset, _: asset,
        )
        engine.agent = SimpleNamespace(
            learner=SimpleNamespace(
                is_asset_in_cooldown=lambda _: False,
                get_asset_confidence_boost=lambda _: 1,
            ),
            evaluate_asset=Mock(return_value={"decision": decision, "confidence": confidence}),
            _add_thought=Mock(),
        )
        engine._execute_buy = Mock()
        engine._evaluate_and_trade(market)
        return engine._execute_buy

    demo = run("PAPER")
    real = run("LIVE_REAL")
    assert demo.call_args_list == real.call_args_list
    if decision == "HOLD":
        demo.assert_not_called()
    else:
        demo.assert_called_once()
        assert demo.call_args.args[0] == "EURUSD"
        assert demo.call_args.args[2]["decision"] == decision


def test_cfd_real_rejects_unarmed_execution_before_broker_send(monkeypatch):
    monkeypatch.setattr(trading_engine, "live_trading_armed", lambda: False)
    monkeypatch.setattr(trading_engine, "live_cfd_execution_verified", lambda: False)
    engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
    engine.broker_wallets = {"IQOPTION": {"environment": "LIVE_REAL", "cash": 10000}}
    engine.iq_mode = "FOREX_CFD"
    submit = Mock()
    engine.feed = SimpleNamespace(iqoption=SimpleNamespace(submit_order=submit))
    engine._execute_buy("EURUSD", {"price": 1.05}, {"decision": "BUY", "confidence": 90})
    submit.assert_not_called()


@pytest.mark.parametrize("direction", ["BUY", "SELL"])
def test_cfd_equal_inputs_generate_equal_broker_arguments(direction, monkeypatch):
    monkeypatch.setattr(trading_engine, "live_trading_armed", lambda: True)
    monkeypatch.setattr(trading_engine, "live_cfd_execution_verified", lambda: True)
    monkeypatch.setattr(trading_engine.time, "time", lambda: 1800000000.0)

    def run(environment):
        engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
        engine.iq_mode = "FOREX_CFD"
        engine.max_loss_enabled = True
        engine.max_loss_amount = 100
        engine.broker_wallets = {"IQOPTION": {
            "environment": environment, "cash": 1000.0,
            "initial_balance": 1000.0, "max_loss_enabled": True,
            "max_loss_amount": 100,
        }}
        engine.open_positions = {}
        engine.last_exit_times = {}
        engine._broker_order_failure_cooldown = {}
        engine._iqoption_order_pending = False
        engine._iqoption_can_open = lambda: True
        engine.get_broker_equity = lambda _: 1000.0
        submit = Mock(return_value={"success": False, "error": "rejected"})
        engine.feed = SimpleNamespace(
            iqoption=SimpleNamespace(currency="USD", get_open_positions=lambda: [], submit_order=submit),
            is_live_data_quality_ok=lambda *args, **kwargs: True,
        )
        engine.agent = SimpleNamespace(
            learner=SimpleNamespace(penalize=Mock()),
            _add_thought=Mock(),
        )
        engine.risk_manager = SimpleNamespace(can_open_trade=Mock(return_value=True))
        decision = {
            "decision": direction, "confidence": 90,
            "budget_percent": 10, "reason_simple": "test",
            "stop_loss": 1.0 if direction == "BUY" else 1.1,
            "take_profit": 1.1 if direction == "BUY" else 1.0,
        }
        engine._execute_buy("EURUSD", {"price": 1.05, "name": "EURUSD"}, decision)
        submit.assert_called_once()
        return submit.call_args.kwargs, engine.risk_manager.can_open_trade.call_args

    demo, demo_risk = run("PAPER")
    real, real_risk = run("LIVE_REAL")
    assert demo == real
    assert demo_risk == real_risk
    assert demo["side"] == ("buy" if direction == "BUY" else "sell")
    assert demo["amount"] == 50.0
    assert demo["leverage"] == 25
