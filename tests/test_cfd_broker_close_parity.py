from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from execution.trading_engine import RealTimeTradingEngine
from risk_management.iqoption_risk_policy import IQOptionRiskPolicy


@pytest.mark.parametrize("environment", ["PAPER", "LIVE_REAL"])
@pytest.mark.parametrize("outcome", ["acknowledged", "exception"])
def test_broker_managed_close_never_books_local_pnl(environment, outcome):
    engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
    engine.active_broker = "IQOPTION"
    engine.iqoption_risk_policy = IQOptionRiskPolicy()
    engine.is_running = True
    engine._iqoption_order_pending = False
    engine.broker_wallets = {
        "IQOPTION": {"environment": environment, "cash": 1000.0, "is_running": True}
    }
    engine.open_positions = {
        "EURUSD": {
            "symbol": "EURUSD",
            "name": "EURUSD",
            "broker": "IQOPTION",
            "category": "FOREX",
            "broker_order_id": "12345",
            "execution_status": "FILLED",
            "entry_price": 1.1,
            "quantity": 1.0,
            "invested_amount": 10.0,
        }
    }
    if outcome == "exception":
        close = Mock(side_effect=TimeoutError("uncertain"))
    else:
        close = Mock(return_value={"success": True, "status": "CLOSE_ACKNOWLEDGED"})
    engine.feed = SimpleNamespace(iqoption=SimpleNamespace(close_position=close))
    engine.agent = SimpleNamespace(_add_thought=Mock(), record_trade_result=Mock())
    engine.journal = SimpleNamespace(record_trade=Mock())

    engine._execute_sell("EURUSD", {"price": 1.2}, {"reason_simple": "test"})

    close.assert_called_once_with("12345")
    assert engine.broker_wallets["IQOPTION"]["cash"] == 1000.0
    engine.journal.record_trade.assert_not_called()
    engine.agent.record_trade_result.assert_not_called()
    assert "EURUSD" in engine.open_positions
    position = engine.open_positions["EURUSD"]
    if outcome == "acknowledged":
        assert position["execution_state"] == "PENDING_CLOSE_RECONCILIATION"
    else:
        assert position["execution_state"] == "UNKNOWN_RECONCILIATION"
        assert engine.iqoption_risk_policy.snapshot()["reconciliation_required"] is True
