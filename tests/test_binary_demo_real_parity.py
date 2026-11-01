from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from execution.trading_engine import RealTimeTradingEngine


@pytest.mark.parametrize("signals", [
    {"EURUSD": ("CALL", 91, 0.88), "GBPUSD": ("PUT", 90, 0.95)},
    {"EURUSD": ("HOLD", 40, 0.88), "GBPUSD": ("HOLD", 30, 0.95)},
])
def test_demo_and_real_evaluate_same_binary_candidates_without_real_order(signals, monkeypatch):
    monkeypatch.setattr("execution.trading_engine.time.time", lambda: 1800000000.0)
    market = {s: {"symbol": s, "category": "FOREX", "price": 1.05} for s in signals}
    snapshot = {
        "closed_candles": [{"time": 1, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05}],
        "current_price": 1.05,
        "current_candle": {"time": 1},
        "refreshed_at": 1.0,
    }

    def run(environment):
        engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
        engine.execution_environment = environment
        engine._iqoption_can_open = lambda: True
        engine.broker_wallets = {"IQOPTION": {"cash": 10000.0, "is_running": True}}
        engine.unavailable_assets_blacklist = {}
        adapter = SimpleNamespace(currency="USD", is_asset_open=lambda _: True)
        engine.feed = SimpleNamespace(
            iqoption=adapter,
            get_verified_iq_market_snapshot=lambda *args, **kwargs: snapshot,
            enrich_asset_from_iq_snapshot=lambda asset, _: asset,
        )
        evaluate = Mock(side_effect=lambda asset, _: {
            "decision": signals[asset["symbol"]][0],
            "confidence": signals[asset["symbol"]][1],
            "payout": signals[asset["symbol"]][2],
            "signal_strategy": "TEST",
            "reason": "fixture",
        })
        execute = Mock(return_value={"success": True, "order_id": "mock"})
        engine.binary_engine = SimpleNamespace(
            global_cooldown_until=0,
            min_confidence=85,
            evaluate_asset=evaluate,
            is_asset_direction_paused=lambda *_: False,
            execute_binary_option=execute,
        )
        engine.agent = SimpleNamespace(_add_thought=Mock())
        engine._evaluate_and_trade_binary(market)
        return evaluate, execute, engine.agent._add_thought, engine

    demo_evaluate, demo_execute, _, _ = run("PAPER")
    real_evaluate, real_execute, real_log, real_engine = run("LIVE_REAL")
    assert [call.args[0]["symbol"] for call in demo_evaluate.call_args_list] == [
        call.args[0]["symbol"] for call in real_evaluate.call_args_list
    ]
    real_execute.assert_not_called()
    if all(signal[0] == "HOLD" for signal in signals.values()):
        demo_execute.assert_not_called()
        assert real_engine._last_binary_blocked_proposal is None
    else:
        demo_execute.assert_called_once()
        order = demo_execute.call_args.kwargs
        assert real_engine._last_binary_blocked_proposal == order
        assert order["symbol"] == "GBPUSD"
        assert order["direction"] == "PUT"
        assert order["amount"] == 2.0
        assert any(
            order["symbol"] in str(call.args[0])
            and order["direction"] in str(call.args[0])
            and "No se envió orden" in str(call.args[0])
            for call in real_log.call_args_list
        )


@pytest.mark.parametrize("soros_enabled,previous_profit", [(False, 0.0), (True, 1.5)])
def test_binary_stake_and_expiry_same_under_identical_risk_state(
    soros_enabled, previous_profit, monkeypatch
):
    from execution.binary_options_engine import BinaryOptionsStrategyEngine
    from risk_management.soros_manager import SorosRiskManager

    monkeypatch.setattr("execution.binary_options_engine.time.time", lambda: 1800000000.0)

    def prepare(environment):
        adapter = SimpleNamespace(
            environment=environment,
            get_payout=lambda _: 0.88,
            submit_binary_option=Mock(return_value={"success": False, "error": "rejected"}),
        )
        engine = BinaryOptionsStrategyEngine.__new__(BinaryOptionsStrategyEngine)
        engine.iq = adapter
        engine.open_position = None
        engine.global_cooldown_until = 0
        engine.min_payout = 0.85
        engine.last_trade_time = {}
        engine.soros_manager = SorosRiskManager(
            base_stake=2, soros_enabled=soros_enabled, max_soros_level=1
        )
        engine.soros_manager.soros_step = int(soros_enabled)
        engine.soros_manager.last_profit = previous_profit
        result = engine.execute_binary_option("EURUSD", "CALL", 2.0, entry_price=1.05)
        assert result["success"] is False
        assert engine.open_position is None
        adapter.submit_binary_option.assert_called_once()
        return adapter.submit_binary_option.call_args.kwargs

    demo = prepare("PAPER")
    real = prepare("LIVE_REAL")
    assert demo == real
    assert demo["amount"] == (3.5 if soros_enabled else 2.0)
    assert demo["direction"] == "CALL"
    assert demo["duration_minutes"] == 1
    assert demo["expiration_timestamp"] > 1800000000.0
