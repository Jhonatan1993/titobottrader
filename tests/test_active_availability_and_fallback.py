import time
import pytest
from unittest.mock import Mock, patch
from execution.trading_engine import RealTimeTradingEngine
from execution.iqoption_adapter import IQOptionAdapter
from execution.binary_options_engine import BinaryOptionsStrategyEngine


def test_is_asset_open_and_silent_scan_filtering():
    """
    Verifica que:
    1. Si un activo está marcado como suspended o enabled=False en _active_status_cache,
       is_asset_open retorna False.
    2. Durante la ronda de escaneo en _evaluate_and_trade_binary, el motor descarta
       silenciosamente el activo suspendido sin generar rechazos de broker.
    """
    engine = RealTimeTradingEngine(max_open_positions=1)
    engine.iq_mode = "BINARY_OPTIONS"
    
    # Configurar adaptador de IQ Option con estado de activos
    adapter = IQOptionAdapter(ssid="test_ssid_123")
    adapter._active_status_cache = {
        "EURGBP-OTC": False,  # Suspendido temporalmente en IQ Option
        "EURUSD-OTC": True,   # Abierto y habilitado
        "USDJPY-OTC": False,  # Suspendido
    }
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    # Verificar consultas directas
    assert adapter.is_asset_open("EURGBP-OTC") is False
    assert adapter.is_asset_open("EURUSD-OTC") is True
    assert adapter.is_asset_open("USDJPY-OTC") is False

    # Verificar que evaluate_asset en binary_options_engine devuelve HOLD con score 0
    asset_eurgbp = {"symbol": "EURGBP-OTC", "category": "FOREX", "price": 0.8382, "rsi": 25.0}
    res_eurgbp = engine.binary_engine.evaluate_asset(asset_eurgbp, candles=[{"time": time.time(), "open": 0.8382, "high": 0.8385, "low": 0.8380, "close": 0.8384, "volume": 100} for _ in range(15)])
    assert res_eurgbp["decision"] == "HOLD"
    assert res_eurgbp["confidence"] == 0
    assert "suspendido o cerrado" in res_eurgbp["reason"]


def test_candidate_fallback_when_top_asset_suspended():
    """
    Verifica que cuando el candidato #1 (ej. EURGBP-OTC) es rechazado por el broker con
    'Cannot purchase an option (active is suspended)', el motor:
    1. Bloquea de inmediato a EURGBP-OTC por 30 minutos (blacklist y disable_asset).
    2. Salta de inmediato en el mismo segundo 58 al candidato #2 calificado (>= 65%),
       ejecutándolo con éxito sin perder la ventana de trading.
    """
    engine = RealTimeTradingEngine(max_open_positions=1)
    engine.iq_mode = "BINARY_OPTIONS"
    engine.broker_wallets["IQOPTION"] = {"cash": 100.0, "is_running": True}

    adapter = IQOptionAdapter(ssid="test_ssid_123")
    adapter._active_status_cache = {
        "EURGBP-OTC": True,  # Inicialmente aparece abierto
        "EURUSD-OTC": True,  # Abierto
    }
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    market_state = {
        "EURGBP-OTC": {"symbol": "EURGBP-OTC", "category": "FOREX", "price": 0.8382},
        "EURUSD-OTC": {"symbol": "EURUSD-OTC", "category": "FOREX", "price": 1.1215},
    }

    # Simular confluencia para ambos:
    # EURGBP-OTC: 78% (Top 1)
    # EURUSD-OTC: 72% (Top 2)
    def fake_evaluate(asset, candles):
        sym = asset.get("symbol")
        if sym == "EURGBP-OTC":
            return {"decision": "PUT", "confidence": 78, "payout": 0.88, "reason": "Mecha bajista + RSI 78"}
        elif sym == "EURUSD-OTC":
            return {"decision": "CALL", "confidence": 72, "payout": 0.85, "reason": "Order Block + RSI 22"}
        return {"decision": "HOLD", "confidence": 0, "payout": 0.0, "reason": "No setup"}

    executed_calls = []
    def fake_execute(symbol, direction, amount, duration_minutes, entry_price, thesis_reason):
        executed_calls.append(symbol)
        if symbol == "EURGBP-OTC":
            return {
                "success": False,
                "error": "Rechazado por IQ Option Binarias: Cannot purchase an option (active is suspended)."
            }
        elif symbol == "EURUSD-OTC":
            return {
                "success": True,
                "order_id": "14399998888",
                "symbol": symbol,
                "direction": direction,
                "amount": amount
            }
        return {"success": False, "error": "Unknown"}

    with patch.object(engine.binary_engine, "evaluate_asset", side_effect=fake_evaluate):
        with patch.object(engine.binary_engine, "execute_binary_option", side_effect=fake_execute):
            engine._evaluate_and_trade_binary(market_state)

    # 1. Verificar que intentó EURGBP-OTC primero, y al fallar saltó a EURUSD-OTC
    assert executed_calls == ["EURGBP-OTC", "EURUSD-OTC"]

    # 2. Verificar que EURGBP-OTC quedó en blacklist por 30 minutos
    assert "EURGBP-OTC" in engine.unavailable_assets_blacklist
    assert engine.unavailable_assets_blacklist["EURGBP-OTC"] > time.time() + 1700.0
    assert engine.binary_engine.is_asset_disabled("EURGBP-OTC") is True
    assert adapter._active_status_cache["EURGBP-OTC"] is False

    # 3. Verificar que la orden de EURUSD-OTC se completó con éxito
    assert engine.broker_wallets["IQOPTION"]["cash"] == 98.0  # Descontó los $2.00


def test_confluence_strict_threshold_rejection():
    """
    Verifica que el umbral de confluencia estricto (>= 65%) rechace cualquier señal
    con confianza inferior (ej. 55% o 64%), emitiendo HOLD y evitando disparar órdenes.
    """
    adapter = IQOptionAdapter()
    engine = BinaryOptionsStrategyEngine(adapter)
    assert engine.min_confidence == 65

    asset = {
        "symbol": "EURUSD-OTC",
        "category": "FOREX",
        "price": 1.1215,
        "rsi": 50.0,  # RSI Neutro sin agotamiento
        "ema20": 1.1215,
        "ema50": 1.1215,
        "support": 1.1100,
        "resistance": 1.1300
    }
    candles = [
        {
            "time": i * 60,
            "open": 1.1210 + ((i % 4) * 0.0002),
            "high": 1.1218 + ((i % 4) * 0.0002),
            "low": 1.1205 + ((i % 4) * 0.0002),
            "close": 1.1212 + ((i % 4) * 0.0002),
            "volume": 100
        }
        for i in range(25)
    ]

    res = engine.evaluate_asset(asset, candles)
    assert res["decision"] == "HOLD"
    assert res["confidence"] < 65
    assert "Filtro de Calidad Activo" in res["reason"] or "Confluencia insuficiente" in res["reason"]
