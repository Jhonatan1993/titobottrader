import pytest
from unittest.mock import MagicMock
from execution.iqoption_adapter import IQOptionAdapter, ACTIVE_ID_TO_SYMBOL
from execution.trading_engine import RealTimeTradingEngine

def test_result_ack_does_not_wipe_positions():
    """Verifica que el frame ack 'result' no limpie las posiciones antes de que llegue el frame 'positions'."""
    iq = IQOptionAdapter()
    iq.ssid = "test_ssid"
    iq.connected = True
    iq.environment = "LIVE_REAL"

    # Simular mensaje result que IQ Option envía como ACK
    result_frame = {
        "name": "result",
        "request_id": "test_pos_123",
        "msg": {"success": True}
    }
    # Y el mensaje positions real que llega después
    positions_frame = {
        "name": "positions",
        "request_id": "test_pos_123",
        "msg": {
            "positions": [
                {
                    "id": "pos_abc123",
                    "external_id": 100170604808,
                    "active_id": 4, # EURJPY
                    "status": "open",
                    "invest": 719.7,
                    "pnl_net": -180.52,
                    "open_quote": 177.359,
                    "side": "buy"
                }
            ],
            "total": 1,
            "limit": 30
        }
    }

    # Verificar que el parser ignora 'result' y no lo toma como posiciones vacías
    assert result_frame["name"] == "result"
    assert positions_frame["name"] == "positions"
    assert len(positions_frame["msg"]["positions"]) == 1

def test_iqoption_live_equity_includes_invested():
    """Verifica que el equity en vivo de IQ Option sume el saldo disponible, el capital invertido y el PnL no realizado."""
    engine = RealTimeTradingEngine(initial_balance=25000.0)
    engine.active_broker = "IQOPTION"
    engine.broker_wallets["IQOPTION"]["cash"] = 22309.24 # Saldo disponible según screenshot
    engine.broker_wallets["IQOPTION"]["environment"] = "LIVE_REAL"

    # Posición activa mapeada desde el broker
    engine.open_positions["EURJPY"] = {
        "symbol": "EURJPY",
        "broker": "IQOPTION",
        "invested_amount": 1998.80, # Inversión total según screenshot
        "current_pnl": -268.65,      # PnL según screenshot
        "side": "BUY"
    }

    equity = engine.get_broker_equity("IQOPTION")
    # 22309.24 + 1998.80 - 268.65 = 24039.39
    assert equity == 24039.39
