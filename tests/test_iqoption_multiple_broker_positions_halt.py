from execution.trading_engine import RealTimeTradingEngine


def test_multiple_iqoption_positions_pause_new_entries():
    """Dos posiciones detectadas en IQ Option deben bloquear cualquier nueva entrada."""
    engine = RealTimeTradingEngine(
        initial_balance=10_000.0,
        execution_environment="PAPER",
    )

    engine._sync_iqoption_open_positions(
        [
            {
                "id": "position-1",
                "active_id": 1,
                "open_quote": 1.10000,
                "invest": 2_000.0,
                "side": "BUY",
            },
            {
                "id": "position-2",
                "active_id": 5,
                "open_quote": 1.25000,
                "invest": 2_000.0,
                "side": "SELL",
            },
        ]
    )

    assert engine.broker_wallets["IQOPTION"]["is_running"] is False
    assert engine.is_running is False
    assert len(engine.get_broker_positions("IQOPTION")) == 2
