from execution.trading_engine import RealTimeTradingEngine


def test_live_cfd_close_waits_for_broker_reconciliation(monkeypatch):
    """Un cierre real no puede acreditar PnL local ni liberar el cupo anticipadamente."""
    engine = RealTimeTradingEngine(
        initial_balance=10_000.0,
        execution_environment="PAPER",
    )
    engine.broker_wallets["IQOPTION"]["environment"] = "LIVE_REAL"
    engine.execution_environment = "LIVE_REAL"

    engine.open_positions["EURUSD"] = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "broker": "IQOPTION",
        "category": "FOREX",
        "broker_order_id": "123456",
        "entry_price": 1.10000,
        "current_price": 1.10000,
        "quantity": 1.0,
        "invested_amount": 2_000.0,
        "current_pnl": 0.0,
        "current_pnl_percent": 0.0,
        "side": "CALL",
    }
    cash_before = engine.broker_wallets["IQOPTION"]["cash"]
    journal_count_before = len(engine.journal.trades)

    monkeypatch.setattr(
        engine.feed.iqoption,
        "close_position",
        lambda position_id: {
            "success": True,
            "status": "CLOSED_REQUEST_ACCEPTED",
            "position_id": position_id,
        },
    )

    engine._execute_sell(
        "EURUSD",
        {"symbol": "EURUSD", "price": 1.10500},
        {"decision": "SELL_TAKE_PROFIT", "reason_simple": "Objetivo alcanzado"},
    )

    position = engine.open_positions["EURUSD"]
    assert position["execution_state"] == "PENDING_CLOSE_RECONCILIATION"
    assert engine.broker_wallets["IQOPTION"]["cash"] == cash_before
    assert len(engine.journal.trades) == journal_count_before
