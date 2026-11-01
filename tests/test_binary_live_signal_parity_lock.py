from unittest.mock import Mock

from execution.iqoption_adapter import IQOptionAdapter
from execution.trading_engine import RealTimeTradingEngine


class SignalOnlyIQAdapter:
    currency = "COP"

    def is_asset_open(self, symbol):
        return True


def test_live_binary_uses_shared_signal_selection_but_never_calls_executor():
    """LIVE_REAL may inspect the same candidate, but the order path stays locked."""
    engine = RealTimeTradingEngine(initial_balance=50_000.0, execution_environment="PAPER")
    engine.execution_environment = "LIVE_REAL"
    engine.iq_mode = "BINARY_OPTIONS"
    engine.broker_wallets["IQOPTION"].update({"cash": 50_000.0, "is_running": True})
    engine.feed.iqoption = SignalOnlyIQAdapter()
    engine._iqoption_can_open = lambda: True

    snapshot = {
        "closed_candles": [{"time": 1, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05}],
        "current_price": 1.05,
        "current_candle": {"time": 1},
        "refreshed_at": 1.0,
    }
    engine.feed.get_verified_iq_market_snapshot = lambda *args, **kwargs: snapshot
    engine.feed.enrich_asset_from_iq_snapshot = lambda asset, _snapshot: asset

    evaluate_asset = Mock(return_value={
        "decision": "CALL",
        "confidence": 91,
        "payout": 0.88,
        "signal_strategy": "TEST_STRATEGY",
        "reason": "test candidate",
    })
    engine.binary_engine.evaluate_asset = evaluate_asset
    engine.binary_engine.is_asset_direction_paused = lambda *_args: False
    execute_binary_option = Mock(side_effect=AssertionError("LIVE_REAL attempted to submit an order"))
    engine.binary_engine.execute_binary_option = execute_binary_option
    engine.agent._add_thought = Mock()

    engine._evaluate_and_trade_binary({
        "EURUSD": {"symbol": "EURUSD", "category": "FOREX", "price": 1.05},
    })

    evaluate_asset.assert_called_once()
    execute_binary_option.assert_not_called()
    assert any(
        "No se envió orden" in str(call.args[0])
        and "score heurístico" in str(call.args[0])
        for call in engine.agent._add_thought.call_args_list
    )
    assert engine.binary_engine.has_active_position is False


def test_binary_adapter_rejects_live_real_before_any_broker_send():
    adapter = IQOptionAdapter(ssid="test-session", environment="PAPER")
    adapter.environment = "LIVE_REAL"
    adapter._execute_real_binary_ws_order = Mock(
        side_effect=AssertionError("broker order function must not be called")
    )

    result = adapter.submit_binary_option("EURUSD", "CALL", 2_000.0)

    assert result["success"] is False
    assert result["execution_blocked"] is True
    assert result["status"] == "BLOCKED"
    adapter._execute_real_binary_ws_order.assert_not_called()
