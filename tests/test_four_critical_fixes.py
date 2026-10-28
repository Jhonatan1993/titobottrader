import time
import pytest
from unittest.mock import MagicMock, patch
from execution.iqoption_adapter import IQOptionAdapter, ACTIVE_ASSET_IDS
from execution.binary_options_engine import BinaryOptionsStrategyEngine
from risk_management.soros_manager import SorosRiskManager
from market_data.market_feed import MultiAssetMarketFeed
from execution.trading_engine import RealTimeTradingEngine


def test_submit_binary_option_payload_and_fallback():
    """Prueba 1: Verifica payload con active y active_id en entero, y fallback si turbo es rechazado."""
    adapter = IQOptionAdapter(ssid="test_ssid_123")
    
    mock_ws = MagicMock()
    sent_payloads = []
    def fake_send(payload_str):
        import json
        sent_payloads.append(json.loads(payload_str))
    
    mock_ws.send.side_effect = fake_send
    mock_ws.recv.side_effect = [
        '{"name": "timeSync", "msg": 1700000000000}',
        '{"name": "profile", "msg": {"balances": [{"id": 12345, "type": 4, "amount": 10000.0}]}}',
        '{"name": "option-rejected", "msg": {"message": "Active %!s(MISSING) not found"}}',
        '{"name": "option-opened", "msg": {"id": 99887766}}'
    ]

    with patch.object(adapter, "_get_persistent_ws", return_value=mock_ws):
        res = adapter._execute_real_binary_ws_order(
            symbol="USDJPY-OTC",
            direction="PUT",
            amount=2.0,
            duration_minutes=1
        )

    # Verificar que el payload inicial incluía 'active' y 'active_id' como enteros
    first_order_payload = next(
        (p for p in sent_payloads if isinstance(p.get("msg"), dict) and p["msg"].get("name") == "binary-options.open-option"),
        None
    )
    assert first_order_payload is not None
    body = first_order_payload["msg"]["body"]
    assert body["active_id"] == 87
    assert body["active"] == 87
    assert isinstance(body["active_id"], int)
    assert isinstance(body["active"], int)
    assert body["direction"] == "put"
    assert body["price"] == 2

    # Verificar que se intentó fallback (option_type_id 1) y se concretó la orden con éxito
    assert res["success"] is True
    assert res["order_id"] == "99887766"


def test_prices_never_corrupted_by_random_walk_or_ratio():
    """Prueba 2: Verifica que EURJPY-OTC y GBPJPY conserven precios reales sin distorsión."""
    feed = MultiAssetMarketFeed()
    
    # 1. Verificar cotización inicial de EURJPY-OTC y GBPJPY
    eurjpy_otc = feed.get_asset("EURJPY-OTC")
    gbpjpy = feed.get_asset("GBPJPY")
    assert eurjpy_otc is not None
    assert eurjpy_otc["price"] > 100.0 # ~175.74
    assert gbpjpy is not None
    assert gbpjpy["price"] > 150.0 and gbpjpy["price"] < 300.0 # ~210.23

    # 2. Asignar velas de IQ Option a EURJPY-OTC
    mock_candles = [
        {"time": int(time.time()) - 120, "open": 175.70, "high": 175.85, "low": 175.68, "close": 175.80, "volume": 150},
        {"time": int(time.time()) - 60, "open": 175.80, "high": 175.92, "low": 175.75, "close": 175.88, "volume": 200}
    ]
    feed.candles["EURJPY-OTC"] = mock_candles

    # 3. Ejecutar varios ticks
    for _ in range(5):
        feed.tick()

    # El precio debe mantenerse anclado a la vela real de IQ Option (~175.88), NUNCA caer a $72 o $87
    cur_p = feed.get_asset("EURJPY-OTC")["price"]
    assert 170.0 < cur_p < 185.0
    assert feed.get_asset("EURJPY-OTC")["source"] == "IQOPTION_REAL_FEED"

    # Y las velas históricas NO deben haber sido multiplicadas por ningún ratio
    assert feed.candles["EURJPY-OTC"][0]["close"] == 175.80


def test_soros_disabled_by_default_fixed_stake():
    """Prueba 3: Verifica que Soros esté apagado por defecto y el stake permanezca fijo en $2.00."""
    dummy_adapter = MagicMock()
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=dummy_adapter)
    assert engine.soros_manager.soros_enabled is False
    assert engine.soros_manager.max_soros_level == 0

    # Stake inicial
    stake1 = engine.soros_manager.calculate_stake(2.0)
    assert stake1 == 2.0

    # Simular operación GANADA de $2.00 (+88% -> profit $1.76)
    res_win = engine.soros_manager.register_trade_result(profit=1.76, invested=2.0)
    assert res_win["soros_step"] == 0 # No avanza paso de Soros

    # La siguiente operación DEBE arriesgar estrictamente el stake fijo de $2.00, NO $3.76
    stake2 = engine.soros_manager.calculate_stake(2.0)
    assert stake2 == 2.0


def test_binary_options_isolated_from_cfd_trailing_stop():
    """Prueba 4: Verifica que en modo BINARY_OPTIONS no se evalúe Trailing Stop de CFDs."""
    engine = RealTimeTradingEngine(max_open_positions=1)
    engine.iq_mode = "BINARY_OPTIONS"

    # Si _sync_iqoption_open_positions recibe posiciones de IQ Option, no debe meterlas a open_positions
    fake_broker_pos = [{
        "id": "14396377264",
        "external_id": "14396377264",
        "symbol": "EURGBP-OTC",
        "active_id": 77,
        "invest": 2.0,
        "pnl_net": 1.74,
        "open_quote": 0.83500,
        "side": "PUT"
    }]
    engine._sync_iqoption_open_positions(fake_broker_pos)
    assert len(engine.open_positions) == 0

    # Simular llamada a step() con pensamiento mockeado
    with patch.object(engine.agent, "_add_thought") as mock_thought:
        engine.step()
        # Verificar que NUNCA se haya emitido "Bloqueo de Ganancia" ni "Trailing Stop"
        for call_args in mock_thought.call_args_list:
            thought_text = str(call_args[0][0])
            assert "Bloqueo de Ganancia" not in thought_text
            assert "Trailing Stop" not in thought_text
            assert "Break-Even Blindado" not in thought_text
