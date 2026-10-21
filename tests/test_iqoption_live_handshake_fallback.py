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

        # Verificar que se envió place-order-temp para forex
        cfd_msgs = [m for m in sent_messages if isinstance(m.get("msg"), dict) and m["msg"].get("name") == "place-order-temp"]
        assert len(cfd_msgs) == 1
        body = cfd_msgs[0]["msg"]["body"]
        assert body["instrument_type"] == "forex"
        assert body["instrument_id"] == "EURUSD"
        assert body["amount"] == 2000.0

        # Blindaje: NUNCA debe contener binary-options
        all_names = [m["msg"].get("name") for m in sent_messages if isinstance(m.get("msg"), dict)]
        assert "binary-options.open-option" not in all_names

def test_iqoption_close_position_cfd():
    """Verifica que close_position utilice el comando oficial close-position sin binarias."""
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

        # Verificar que se envió close-position v1.0
        close_msgs = [m for m in sent_messages if isinstance(m.get("msg"), dict) and m["msg"].get("name") == "close-position"]
        assert len(close_msgs) == 1
        assert close_msgs[0]["msg"]["body"]["position_id"] == 1499201928

        # Blindaje: CERO sell-options
        all_names = [m["msg"].get("name") for m in sent_messages if isinstance(m.get("msg"), dict)]
        assert "sell-options" not in all_names
