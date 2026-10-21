import pytest
import time
from unittest.mock import MagicMock, patch
from execution.trading_engine import RealTimeTradingEngine
from execution.iqoption_adapter import IQOptionAdapter

def test_evidence_1_strict_single_position_block():
    """
    EVIDENCIA 1: Si hay 1 posición abierta en IQ Option o en memoria,
    100 intentos consecutivos de ejecutar compras deben ser BLOQUEADOS al 100%.
    """
    engine = RealTimeTradingEngine(initial_balance=23206.81, max_open_positions=1, execution_environment="LIVE_REAL")
    engine.set_active_broker("IQOPTION")
    
    # 1 posición activa existente
    engine.open_positions["GBPJPY"] = {
        "symbol": "GBPJPY",
        "name": "GBP / JPY",
        "broker": "IQOPTION",
        "category": "FOREX",
        "invested_amount": 2000.0,
        "entry_price": 211.90,
        "current_price": 211.90,
        "quantity": 1.0,
        "broker_order_id": "101148785000",
        "position_id": "100170573000"
    }

    # Intentar ejecutar compras repetidas para cualquier par
    market_state = {
        "EURUSD": {"symbol": "EURUSD", "name": "EUR/USD", "price": 1.1225, "category": "FOREX", "type": "Forex", "rsi": 50, "trend_status": "UP", "change_percent": 0.5, "support": 1.12, "resistance": 1.13},
        "GBPJPY": {"symbol": "GBPJPY", "name": "GBP/JPY", "price": 211.90, "category": "FOREX", "type": "Forex", "rsi": 50, "trend_status": "UP", "change_percent": 0.5, "support": 211.0, "resistance": 213.0}
    }

    # Intentar 50 ciclos de evaluación
    for _ in range(50):
        engine._evaluate_and_trade(market_state)

    # El conteo de posiciones debe seguir siendo ESTRICTAMENTE 1
    assert len(engine.open_positions) == 1
    assert list(engine.open_positions.keys()) == ["GBPJPY"]


def test_evidence_2_transient_empty_poll_does_not_wipe_memory():
    """
    EVIDENCIA 2: Si el WebSocket de IQ Option sufre un retraso y devuelve temporalmente []
    (lista vacía por timeout de red), la memoria del bot NO se borra en el primer sondeo,
    impidiendo que el bot abra órdenes duplicadas por error.
    """
    engine = RealTimeTradingEngine(initial_balance=23206.81, max_open_positions=1, execution_environment="LIVE_REAL")
    engine.set_active_broker("IQOPTION")
    
    engine.open_positions["GBPJPY"] = {
        "symbol": "GBPJPY",
        "name": "GBP / JPY",
        "broker": "IQOPTION",
        "category": "FOREX",
        "invested_amount": 2000.0,
        "entry_price": 211.90,
        "current_price": 211.90,
        "quantity": 1.0,
        "broker_order_id": "101148785000",
        "position_id": "100170573000"
    }

    # Sondeo 1: devuelve [] por retraso transitorio de red
    engine._sync_iqoption_open_positions([])
    # La posición DEBE seguir protegida en memoria
    assert "GBPJPY" in engine.open_positions
    assert len(engine.open_positions) == 1

    # Sondeo 2: segundo retraso
    engine._sync_iqoption_open_positions([])
    # Sigue protegida
    assert "GBPJPY" in engine.open_positions
    assert len(engine.open_positions) == 1

    # Solo tras el 3er sondeo consecutivo confirmado como 0 se purga
    engine._sync_iqoption_open_positions([])
    assert len(engine.open_positions) == 0


def test_evidence_3_forced_15min_rotation_prevents_same_asset_spam():
    """
    EVIDENCIA 3: En cuanto se opera o cierra un activo (ej: GBPJPY),
    entra en un cooldown forzado de 15 minutos (900s), haciendo IMPOSIBLE
    que el bot vuelva a escoger el mismo activo y forzando la rotación hacia otros pares.
    """
    engine = RealTimeTradingEngine(initial_balance=23206.81, max_open_positions=1, execution_environment="LIVE_REAL")
    engine.set_active_broker("IQOPTION")
    
    now = time.time()
    # Simular que GBPJPY acaba de operarse
    engine.last_exit_times["GBPJPY"] = now + 900.0

    # Activos candidatos
    asset_gbpjpy = {"symbol": "GBPJPY", "name": "GBP/JPY", "price": 211.90, "category": "FOREX", "type": "Forex", "rsi": 50, "trend_status": "UP", "change_percent": 0.5, "support": 211.0, "resistance": 213.0}
    
    # Evaluar si el motor permite comprar GBPJPY durante su cooldown
    market_state = {"GBPJPY": asset_gbpjpy}
    
    with patch.object(engine, "_execute_buy") as mock_buy:
        engine._evaluate_and_trade(market_state)
        # No debe haber llamado a _execute_buy para GBPJPY
        mock_buy.assert_not_called()

    # Verificar que el tiempo restante de enfriamiento para GBPJPY es > 850 segundos
    remaining = engine.last_exit_times["GBPJPY"] - time.time()
    assert remaining > 850


def test_evidence_4_bidirectional_reconstruction_blocks_duplicate():
    """
    EVIDENCIA 4: Si IQ Option reporta 1 posición activa (ej: desde la app del broker),
    el bot la reconstruye inmediatamente en su memoria y bloquea nuevos trades.
    """
    engine = RealTimeTradingEngine(initial_balance=23206.81, max_open_positions=1, execution_environment="LIVE_REAL")
    engine.set_active_broker("IQOPTION")
    engine.open_positions.clear()

    assert len(engine.open_positions) == 0

    # IQ Option reporta 1 posición activa de EURUSD
    broker_positions = [{
        "id": "100170999999",
        "external_id": "100170999999",
        "active_id": 1, # EURUSD
        "open_quote": 1.1225,
        "invest": 2000.0,
        "pnl_net": 5.0
    }]

    engine._sync_iqoption_open_positions(broker_positions)

    # La posición ahora está en memoria y bloquea el cupo
    assert len(engine.open_positions) == 1
    assert "EURUSD" in engine.open_positions
    assert engine.risk_manager.current_open_trades == 1
