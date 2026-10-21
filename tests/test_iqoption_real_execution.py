import time
import pytest
from unittest.mock import MagicMock, patch
from execution.iqoption_adapter import IQOptionAdapter, ACTIVE_ASSET_IDS
from execution.trading_engine import RealTimeTradingEngine

def test_iqoption_active_asset_ids_mapping():
    """Verifica que todos los pares mayores de Forex estén correctamente mapeados a sus IDs oficiales de IQ Option"""
    assert ACTIVE_ASSET_IDS["EURUSD"] == 1
    assert ACTIVE_ASSET_IDS["EURGBP"] == 2
    assert ACTIVE_ASSET_IDS["GBPJPY"] == 3
    assert ACTIVE_ASSET_IDS["EURJPY"] == 4
    assert ACTIVE_ASSET_IDS["GBPUSD"] == 5
    assert ACTIVE_ASSET_IDS["USDJPY"] == 6
    assert ACTIVE_ASSET_IDS["AUDUSD"] == 99
    assert ACTIVE_ASSET_IDS["USDCAD"] == 100

def test_iqoption_paper_mode_returns_simulated_order():
    """En entorno PAPER, submit_order debe retornar una orden simulada sin tocar la red real"""
    adapter = IQOptionAdapter(ssid="mock_ssid_123", environment="PAPER")
    res = adapter.submit_order("EURUSD", "BUY", 10.0)
    assert res["success"] is True
    assert res["environment"] == "PAPER"
    assert res["status"] == "FILLED_SIMULATED"
    assert res["symbol"] == "EURUSD"
    assert res["amount"] == 10.0
    assert str(res["order_id"]).startswith("IQ_PAPER_")

def test_iqoption_real_mode_prevents_order_when_balance_zero():
    """En entorno LIVE_REAL, si el saldo real es 0.0, la orden debe ser prevenida con un error claro"""
    adapter = IQOptionAdapter(ssid="mock_ssid_123", environment="LIVE_REAL")
    adapter.connected = True
    adapter.real_amount = 0.0
    adapter.balance = 0.0

    res = adapter.submit_order("EURUSD", "BUY", 15.0)
    assert res["success"] is False
    assert "Saldo insuficiente" in res["error"]

def test_iqoption_real_mode_executes_ws_order_when_balance_available():
    """En entorno LIVE_REAL con saldo real, submit_order debe enviar la orden vía WebSocket y capturar el ID real"""
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True
    adapter.real_amount = 50000.0  # 50,000 COP
    adapter.balance = 50000.0
    adapter.real_balance_id = 999123

    # Simular la conexión y respuesta del WebSocket de IQ Option
    mock_ws = MagicMock()
    mock_responses = [
        '{"name": "timeSync", "msg": 1729000000}',
        '{"name": "order-placed", "msg": {"id": "184920491", "order_id": "184920491"}}'
    ]
    mock_ws.recv.side_effect = mock_responses

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.submit_order("EURUSD", "BUY", 10000.0)
        assert res["success"] is True
        assert res["environment"] == "LIVE_REAL"
        assert res["status"] == "FILLED"
        assert res["order_id"] == "184920491"
        assert res["amount"] == 10000.0

def test_iqoption_trading_engine_environment_switch_cleans_paper_positions():
    """Al conmutar IQ Option de PAPER a LIVE_REAL en el motor, las posiciones demo previas deben limpiarse de inmediato"""
    engine = RealTimeTradingEngine(initial_balance=10000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")

    # Inyectar una posición simulada previa en IQ Option
    engine.open_positions["EURUSD"] = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "broker": "IQOPTION",
        "category": "FOREX",
        "invested_amount": 50.0,
        "entry_price": 1.085,
        "current_price": 1.085,
        "quantity": 46.08
    }
    assert "EURUSD" in engine.open_positions

    # Configurar mock de credenciales y conexión real exitosa para IQ Option
    engine.feed.iqoption.ssid = "test_ssid_valid"
    engine.feed.iqoption.is_configured = True
    with patch.object(engine.feed.iqoption, "connect", return_value={
        "connected": True,
        "name": "Trader Test",
        "real_balance": 150000.0,
        "currency": "COP"
    }):
        switch_res = engine.set_execution_environment("LIVE_REAL", broker="IQOPTION")
        assert switch_res["success"] is True
        assert engine.broker_wallets["IQOPTION"]["environment"] == "LIVE_REAL"
        assert engine.broker_wallets["IQOPTION"]["cash"] == 150000.0

        # La posición simulada de paper DEBE haber sido purgada de las posiciones abiertas
        assert "EURUSD" not in engine.open_positions

def test_iqoption_vault_isolation_between_paper_and_real():
    """Verifica que la bóveda de ganancias de IQ Option en PAPER nunca se mezcle con la de LIVE_REAL"""
    engine = RealTimeTradingEngine(initial_balance=10000.0, execution_environment="PAPER")
    
    # Inicializar explícitamente bóvedas para el test
    engine.save_broker_vault("IQOPTION", 0.0, env="LIVE_REAL")
    engine.save_broker_vault("IQOPTION", 371.29, env="PAPER")

    assert engine.get_broker_vault("IQOPTION", "PAPER") == 371.29
    assert engine.get_broker_vault("IQOPTION", "LIVE_REAL") == 0.0

    # Guardar ganancias en Real
    engine.save_broker_vault("IQOPTION", 50.0, env="LIVE_REAL")
    assert engine.get_broker_vault("IQOPTION", "LIVE_REAL") == 50.0
    assert engine.get_broker_vault("IQOPTION", "PAPER") == 371.29

    # Limpiar estado real después del test
    engine.save_broker_vault("IQOPTION", 0.0, env="LIVE_REAL")

def test_iqoption_pause_isolation_leaves_alpaca_and_binance_untouched():
    """Verifica que al pausar IQ Option, Binance y Alpaca sigan operando normalmente"""
    engine = RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    
    # Pausar únicamente IQ Option
    engine.toggle_pause(broker="IQOPTION")
    assert engine.broker_wallets["IQOPTION"]["is_running"] is False

    # Binance y Alpaca continúan activos
    assert engine.broker_wallets["BINANCE"]["is_running"] is True
    assert engine.broker_wallets["ALPACA"]["is_running"] is True

def test_iqoption_emergency_close_closes_only_forex_positions():
    """Parada de emergencia en IQ Option solo debe cerrar posiciones de IQ Option, dejando intactas las de Binance y Alpaca"""
    engine = RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    
    # Inyectar una posición en cada broker
    engine.open_positions["BTC"] = {
        "symbol": "BTC",
        "name": "Bitcoin",
        "broker": "BINANCE",
        "category": "CRYPTO",
        "invested_amount": 20.0,
        "entry_price": 60000.0,
        "current_price": 60000.0,
        "quantity": 0.00033
    }
    engine.open_positions["AAPL"] = {
        "symbol": "AAPL",
        "name": "Apple",
        "broker": "ALPACA",
        "category": "TRADFI_STOCK",
        "invested_amount": 20.0,
        "entry_price": 220.0,
        "current_price": 220.0,
        "quantity": 0.09
    }
    engine.open_positions["EURUSD"] = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "broker": "IQOPTION",
        "category": "FOREX",
        "invested_amount": 20.0,
        "entry_price": 1.085,
        "current_price": 1.085,
        "quantity": 18.43
    }

    assert len(engine.open_positions) == 3

    # Ejecutar parada de emergencia EXCLUSIVA para IQ Option
    engine.emergency_close_all(broker="IQOPTION")

    # EURUSD debe haberse cerrado
    assert "EURUSD" not in engine.open_positions
    # BTC y AAPL DEBEN seguir abiertas e intactas
    assert "BTC" in engine.open_positions
    assert "AAPL" in engine.open_positions
    # Solo IQ Option debe estar pausado
    assert engine.broker_wallets["IQOPTION"]["is_running"] is False
    assert engine.broker_wallets["BINANCE"]["is_running"] is True
    assert engine.broker_wallets["ALPACA"]["is_running"] is True

def test_iqoption_otc_24_7_resolution_weekdays_and_weekends():
    """Verifica que los activos OTC operen 24/7 tanto en días de semana como en fines de semana"""
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True
    adapter.real_amount = 50000.0
    adapter.balance = 50000.0
    adapter.real_balance_id = 999123

    mock_ws = MagicMock()
    mock_ws.recv.side_effect = [
        '{"name": "timeSync", "msg": 1729000000}',
        '{"status": 2000, "name": "order-placed-temp", "msg": {"id": 14365301803, "active_id": 76}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        # Simular día de semana (Miércoles, weekday=2)
        mock_weekday = MagicMock()
        mock_weekday.weekday.return_value = 2
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = mock_weekday
            res = adapter.submit_order("EURUSD-OTC", "BUY", 2000.0)
            assert res["success"] is True
            assert res["status"] == "FILLED"
            assert res["order_id"] == "14365301803"

def test_iqoption_forex_cfd_websocket_payload_structure():
    """Garantiza que la orden enviada por WebSocket a IQ Option sea 100% Forex CFD y NUNCA Opciones Binarias"""
    import json
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True
    adapter.real_amount = 100000.0
    adapter.balance = 100000.0
    adapter.real_balance_id = 123456

    sent_messages = []
    mock_ws = MagicMock()
    def mock_send(msg):
        sent_messages.append(json.loads(msg))
    mock_ws.send.side_effect = mock_send
    mock_ws.recv.side_effect = [
        '{"name": "profile", "msg": {}}',
        '{"name": "order-placed-temp", "status": 2000, "msg": {"id": 888777, "position_id": 888777}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.submit_order("EURUSD", "BUY", 5000.0, leverage=25, stop_loss_pct=1.2, take_profit_pct=3.5)
        assert res["success"] is True
        assert res["order_id"] == "888777"
        assert res["side"] == "buy"
        assert res["leverage"] == 25

        # Analizar todos los mensajes transmitidos por el WebSocket
        cfd_msg = next(m for m in sent_messages if m.get("name") == "sendMessage")
        msg_body = cfd_msg["msg"]["body"]

        # Verificaciones estrictas de Forex CFD:
        assert cfd_msg["msg"]["name"] == "marginal-forex.place-market-order"
        assert msg_body["instrument_id"] == "mf.1"
        assert msg_body["instrument_active_id"] == 1
        assert msg_body["side"] == "buy"
        assert msg_body["count"] == "100"
        assert msg_body["leverage"] == "25"
        assert msg_body["stop_loss"]["value"] == "1.2"
        assert msg_body["take_profit"]["value"] == "3.5"

        # PROHIBICIÓN ABSOLUTA: Verificar ausencia de cualquier vestigio de binarias
        raw_dump = json.dumps(sent_messages)
        assert "binary-options.open-option" not in raw_dump
        assert "option_type_id" not in raw_dump
        assert "expired" not in raw_dump

def test_iqoption_close_position_websocket_payload():
    """Garantiza que el cierre de posición use close-position de CFD y NUNCA venta de opciones binarias"""
    import json
    adapter = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter.connected = True

    sent_messages = []
    mock_ws = MagicMock()
    def mock_send(msg):
        sent_messages.append(json.loads(msg))
    mock_ws.send.side_effect = mock_send
    mock_ws.recv.side_effect = [
        '{"name": "front", "msg": {}}',
        '{"name": "position-closed", "status": 2000, "msg": {"position_id": 999111}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        res = adapter.close_position("999111")
        assert res["success"] is True
        assert res["status"] == "CLOSED"
        assert res["position_id"] == "999111"

        close_msg = next(m for m in sent_messages if m.get("name") == "sendMessage")
        assert close_msg["msg"]["name"] == "marginal-forex.close-position"
        assert close_msg["msg"]["body"]["position_id"] == 999111

        # PROHIBICIÓN ABSOLUTA:
        raw_dump = json.dumps(sent_messages)
        assert "binary-options.sell-option" not in raw_dump
        assert "options_ids" not in raw_dump


def test_iqoption_sync_purges_ghost_closed_positions():
    """Garantiza que si una posición se cierra en IQ Option (ej: Take Profit), el motor la elimine y libere cupos"""
    engine = RealTimeTradingEngine(initial_balance=26393.26, max_open_positions=1, execution_environment="LIVE_REAL")
    engine.set_active_broker("IQOPTION")

    # Inyectar posición activa simulando que fue abierta
    engine.open_positions["GBPJPY"] = {
        "symbol": "GBPJPY",
        "name": "GBP / JPY",
        "broker": "IQOPTION",
        "category": "FOREX",
        "invested_amount": 2000.0,
        "entry_price": 211.442,
        "current_price": 211.435,
        "quantity": 9.4589,
        "broker_order_id": "101148750757",
        "position_id": "100170562894"
    }

    assert len(engine.open_positions) == 1
    # Cuando IQ Option reporta que el portafolio tiene 0 posiciones abiertas (se cerró en broker)
    engine._sync_iqoption_open_positions([])

    # Debe ser purgada de la memoria y cupo liberado
    assert len(engine.open_positions) == 0
    assert "GBPJPY" not in engine.open_positions

