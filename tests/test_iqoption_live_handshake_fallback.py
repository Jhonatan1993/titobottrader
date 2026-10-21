import json
import pytest
from unittest.mock import MagicMock, patch
from execution.iqoption_adapter import IQOptionAdapter

def test_iqoption_invalid_contract_triggers_resilient_fallback():
    """Verifica que si IQ Option rechaza place-order-temp con 'Invalid contract', el adaptador active inmediatamente el contrato de mercado nativo sin abortar la orden."""
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

    # Simular handshake autenticado, rechazo inicial por 'Invalid contract' en CFD y confirmación exitosa en contrato de mercado
    mock_ws.recv.side_effect = [
        '{"name": "authenticated", "msg": true}',
        '{"name": "result", "request_id": "tito_123", "msg": {"success": false, "reason": "Invalid contract"}}',
        '{"name": "option", "request_id": "tito_opt_456", "msg": {"id": 1499201928, "act": 76, "dir": "call"}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.submit_order("EURUSD-OTC", "BUY", 2000.0)
        assert res["success"] is True
        assert res["status"] == "FILLED"
        assert res["order_id"] == "1499201928"
        assert res["symbol"] == "EURUSD-OTC"

        # Verificar que se intentó place-order-temp y luego se envió el contrato de mercado nativo
        msg_names = [m.get("msg", {}).get("name") for m in sent_messages if m.get("name") == "sendMessage"]
        assert "place-order-temp" in msg_names
        assert "binary-options.open-option" in msg_names

def test_iqoption_close_position_fallback_to_sell_options():
    """Verifica que al cerrar una posición, si close-position no responde o da error, se active sell-options para garantizar salida inmediata."""
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True

    sent_messages = []
    mock_ws = MagicMock()
    def mock_send(msg):
        sent_messages.append(json.loads(msg))
    mock_ws.send.side_effect = mock_send

    # Simular error en close-position y éxito inmediato en sell-options
    mock_ws.recv.side_effect = [
        '{"name": "authenticated", "msg": true}',
        '{"name": "error", "error": "Position not found in CFD engine"}',
        '{"name": "sold-options", "msg": {"1499201928": {"buyback_state": "sold"}}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.close_position("1499201928")
        assert res["success"] is True
        assert res["status"] == "CLOSED"
        assert res["position_id"] == "1499201928"

        msg_names = [m.get("msg", {}).get("name") for m in sent_messages if m.get("name") == "sendMessage"]
        assert "close-position" in msg_names
        assert "sell-options" in msg_names
