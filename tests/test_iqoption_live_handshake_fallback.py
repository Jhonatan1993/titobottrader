import json
import pytest
from unittest.mock import MagicMock, patch
from execution.iqoption_adapter import IQOptionAdapter

def test_iqoption_protocol3_handshake_and_forex_cfd_order():
    """Verifica autenticación protocolo 3 y envío 100% Forex CFD vía place-order-temp sin binarias."""
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True
    adapter.real_amount = 50000.0
    adapter.balance = 50000.0
    adapter.real_balance_id = 999123

    sent_messages = []
    mock_ws = MagicMock()
    def mock_send(msg):
        sent_messages.append(json.loads(msg))
    mock_ws.send.side_effect = mock_send

    mock_ws.recv.side_effect = [
        '{"name": "authenticated", "msg": true}',
        '{"name": "order-placed-temp", "request_id": "tito_123", "msg": {"id": 1499201928, "status": "filled"}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.submit_order("EURUSD", "BUY", 2000.0, leverage=50)
        assert res["success"] is True
        assert res["status"] == "FILLED"
        assert res["order_id"] == "1499201928"
        assert res["symbol"] == "EURUSD"

        # Verificar autenticación protocol 3 y setOptions
        auth_msgs = [m for m in sent_messages if m.get("name") == "authenticate"]
        assert len(auth_msgs) == 1
        assert auth_msgs[0]["msg"]["protocol"] == 3

        # Verificar que se envió marginal-forex.place-market-order para forex CFD
        cfd_msgs = [m for m in sent_messages if isinstance(m.get("msg"), dict) and m["msg"].get("name") == "marginal-forex.place-market-order"]
        assert len(cfd_msgs) == 1
        body = cfd_msgs[0]["msg"]["body"]
        assert body["instrument_id"] == "mf.1"
        assert body["instrument_active_id"] == 1
        assert body["count"] == "100"

        # Blindaje: NUNCA debe contener binary-options
        all_names = [m["msg"].get("name") for m in sent_messages if isinstance(m.get("msg"), dict)]
        assert "binary-options.open-option" not in all_names

def test_iqoption_close_position_cfd():
    """Verifica que close_position utilice el comando oficial marginal-forex.close-position sin binarias."""
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True

    sent_messages = []
    mock_ws = MagicMock()
    def mock_send(msg):
        sent_messages.append(json.loads(msg))
    mock_ws.send.side_effect = mock_send

    mock_ws.recv.side_effect = [
        '{"name": "authenticated", "msg": true}',
        '{"name": "position-closed", "msg": {"position_id": 1499201928}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.close_position("1499201928")
        assert res["success"] is True
        assert res["status"] == "CLOSED"

        # Verificar que se envió marginal-forex.close-position v1.0
        close_msgs = [m for m in sent_messages if isinstance(m.get("msg"), dict) and m["msg"].get("name") == "marginal-forex.close-position"]
        assert len(close_msgs) == 1
        assert close_msgs[0]["msg"]["body"]["position_id"] == 1499201928

        # Blindaje: CERO sell-options
        all_names = [m["msg"].get("name") for m in sent_messages if isinstance(m.get("msg"), dict)]
        assert "sell-options" not in all_names

def test_iqoption_set_options_ack_does_not_trigger_false_order_fill():
    """Verifica que la confirmación de setOptions (status 2000) no sea confundida con una orden ejecutada."""
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True
    adapter.real_amount = 50000.0
    adapter.balance = 50000.0
    adapter.real_balance_id = 999123

    mock_ws = MagicMock()
    mock_ws.recv.side_effect = [
        '{"name": "authenticated", "msg": true}',
        '{"name": "setOptions", "request_id": "set_opts", "status": 2000}',
        '{"name": "order-placed-temp", "request_id": "tito_123", "msg": {"id": 987654321, "status": "filled"}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.submit_order("EURUSD", "BUY", 2000.0, leverage=50)
        assert res["success"] is True
        # Debe haber tomado el ID real de la orden (987654321), NUNCA 'set_opts'
        assert res["order_id"] == "987654321"

def test_trading_engine_failure_cooldown_and_zero_balance_fluctuation():
    """Verifica que si la orden es rechazada por el broker, el saldo local no sufre deducciones fantasma."""
    from execution.trading_engine import RealTimeTradingEngine

    engine = RealTimeTradingEngine(initial_balance=26429.61)
    engine.broker_wallets["IQOPTION"]["cash"] = 26429.61
    engine.broker_wallets["IQOPTION"]["environment"] = "LIVE_REAL"
    engine.broker_wallets["IQOPTION"]["cash"] = 26429.61
    engine.broker_wallets["IQOPTION"]["environment"] = "LIVE_REAL"

    # Simular fallo en IQ Option (ej. mercado cerrado o contrato suspendido)
    engine.feed.iqoption.submit_order = MagicMock(return_value={"success": False, "error": "Market is closed"})

    asset = {"symbol": "EURUSD", "name": "EUR/USD", "price": 1.0850, "category": "FOREX"}
    decision = {"decision": "BUY", "confidence": 92, "reason_simple": "Señal fuerte"}

    # Ejecutar compra
    engine._execute_buy("EURUSD", asset, decision, broker_id="IQOPTION")

    # El saldo NUNCA debió haber bajado ni fluctuado
    assert engine.broker_wallets["IQOPTION"]["cash"] == 26429.61
    assert "EURUSD" not in engine.open_positions
    # El broker debe haber entrado en cooldown de 30s
    assert engine._broker_order_failure_cooldown.get("IQOPTION", 0) > 0

