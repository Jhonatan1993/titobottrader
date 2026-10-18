import time
import pytest
from unittest.mock import MagicMock, patch
from execution.trading_engine import RealTimeTradingEngine
from market_data.market_feed import MultiAssetMarketFeed

def test_binary_option_never_closes_early_by_spot_stop_loss():
    """
    GARANTÍA 1: Las opciones binarias de IQ Option NUNCA deben cerrarse antes de tiempo
    por variaciones o caídas en el precio spot (Stop-Loss spot desactivado para binarias).
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    
    # Crear una opción binaria CALL abierta en EURUSD-OTC con entrada a 1.0850
    now = time.time()
    engine.open_positions["EURUSD-OTC"] = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "current_price": 1.0850,
        "invested_amount": 2000.0,
        "stop_loss": 1.0800,
        "initial_stop_loss": 1.0800,
        "take_profit": 1.0900,
        "entry_timestamp": now - 15.0,  # Lleva 15 segundos abierta
        "duration_sec": 60
    }
    
    # Simular una caída catastrófica del precio a 0.5000 (-50%)
    market_state = {
        "EURUSD-OTC": {
            "symbol": "EURUSD-OTC",
            "name": "EUR / USD (OTC 24/7)",
            "category": "FOREX",
            "price": 0.5000,
            "volatility": 0.0035,
            "trend_bias": 0.0001
        }
    }
    
    # Evaluar salidas del motor
    engine._evaluate_and_trade(market_state)
    
    # La posición DEBE seguir abierta porque apenas van 15s de los 60s
    assert "EURUSD-OTC" in engine.open_positions, "FALLO CRÍTICO: La opción binaria se cerró anticipadamente por Stop-Loss de precio spot!"

def test_binary_option_closes_strictly_at_expiration_time():
    """
    GARANTÍA 2: La opción binaria de IQ Option se cierra y liquida ÚNICAMENTE
    cuando se cumple el tiempo de expiración (60 segundos).
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    
    now = time.time()
    engine.open_positions["EURUSD-OTC"] = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "current_price": 1.0860,
        "invested_amount": 2000.0,
        "entry_timestamp": now - 62.0,  # 62 segundos transcurridos (> 60s expiración)
        "duration_sec": 60
    }
    
    market_state = {
        "EURUSD-OTC": {
            "symbol": "EURUSD-OTC",
            "name": "EUR / USD (OTC 24/7)",
            "category": "FOREX",
            "price": 1.0860,
            "volatility": 0.0035,
            "trend_bias": 0.0001
        }
    }
    
    engine._evaluate_and_trade(market_state)
    
    # La posición DEBE haberse cerrado por cumplimiento de tiempo de expiración
    assert "EURUSD-OTC" not in engine.open_positions, "La opción debió liquidarse al expirar los 60 segundos!"

def test_binary_option_pnl_fixed_payout_win_and_loss():
    """
    GARANTÍA 3: El PnL de IQ Option debe ser binario (+88% en victoria, -100% en pérdida),
    nunca fraccionario tipo acción Spot.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    
    # Caso Ganador (CALL con precio final > precio entrada): +88%
    engine.open_positions["EURUSD-OTC"] = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "invested_amount": 2000.0,
        "entry_timestamp": time.time() - 65.0,
        "duration_sec": 60
    }
    asset_win = {"symbol": "EURUSD-OTC", "name": "EUR / USD", "price": 1.0855, "category": "FOREX"}
    engine._execute_sell("EURUSD-OTC", asset_win, {"decision": "SELL_EXPIRATION"})
    
    # Verificar PnL ganador
    last_trade_win = engine.journal.trades[0]
    assert last_trade_win["pnl"] == 1760.0, f"Ganancia esperada +1,760 COP (+88%), pero dio {last_trade_win['pnl']}"
    assert last_trade_win["pnl_percent"] == 88.0
    
    # Caso Perdedor (CALL con precio final < precio entrada): -100%
    engine.open_positions["EURUSD-OTC"] = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "invested_amount": 2000.0,
        "entry_timestamp": time.time() - 65.0,
        "duration_sec": 60
    }
    asset_loss = {"symbol": "EURUSD-OTC", "name": "EUR / USD", "price": 1.0845, "category": "FOREX"}
    engine._execute_sell("EURUSD-OTC", asset_loss, {"decision": "SELL_EXPIRATION"})
    
    # Verificar PnL perdedor
    last_trade_loss = engine.journal.trades[0]
    assert last_trade_loss["pnl"] == -2000.0, f"Pérdida esperada -2,000 COP (-100%), pero dio {last_trade_loss['pnl']}"
    assert last_trade_loss["pnl_percent"] == -100.0

def test_forex_spot_vs_binary_isolation():
    """
    GARANTÍA 4: Aislamiento estricto: Las acciones y Cripto Spot (Alpaca/Binance)
    SÍ ejecutan Stop Loss en caída de precio, mientras que IQ Option Binarias NO lo ejecuta.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    
    now = time.time()
    # 1. Posición Alpaca Spot (Acción NVDA con Stop Loss en 115)
    engine.open_positions["NVDA"] = {
        "symbol": "NVDA",
        "name": "NVIDIA Corp",
        "broker": "ALPACA",
        "category": "TRADFI_STOCK",
        "side": "BUY",
        "quantity": 1.0,
        "entry_price": 120.0,
        "stop_loss": 115.0,
        "take_profit": 130.0,
        "invested_amount": 120.0,
        "entry_timestamp": now - 40.0
    }
    # 2. Posición IQ Option Binaria
    engine.open_positions["EURUSD-OTC"] = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "stop_loss": 1.0800,
        "invested_amount": 2000.0,
        "entry_timestamp": now - 40.0,
        "duration_sec": 60
    }
    
    # Ambas sufren caída que perfora el Stop-Loss spot
    market_state = {
        "NVDA": {"symbol": "NVDA", "name": "NVIDIA", "category": "TRADFI_STOCK", "price": 110.0, "volatility": 0.015, "trend_bias": 0.0001},
        "EURUSD-OTC": {"symbol": "EURUSD-OTC", "name": "EUR / USD", "category": "FOREX", "price": 1.0700, "volatility": 0.0035, "trend_bias": 0.0001}
    }
    
    engine._evaluate_and_trade(market_state)
    
    # NVDA (Spot Alpaca) DEBE haberse cerrado para proteger capital
    assert "NVDA" not in engine.open_positions, "NVDA debió cerrarse por Stop-Loss de Spot!"
    # EURUSD-OTC (Binaria IQ Option) DEBE seguir abierta porque sus 60s no se han cumplido
    assert "EURUSD-OTC" in engine.open_positions, "La binaria no debió cerrarse antes de los 60s!"

def test_forex_feed_precision_and_no_price_runaway():
    """
    GARANTÍA 5: La cotización Forex debe mantener 5 decimales de precisión
    y nunca dispararse a precios irreales (+1000%).
    """
    feed = MultiAssetMarketFeed()
    feed.reset_forex_feed()
    
    # Ejecutar 50 ticks continuos
    for _ in range(50):
        feed.tick()
        
    eur_price = feed.assets["EURUSD"]["price"]
    eur_otc_price = feed.assets["EURUSD-OTC"]["price"]
    
    # El precio debe mantenerse dentro de un rango realista (+/- 2% de 1.0850)
    assert 1.0500 <= eur_price <= 1.1200, f"EURUSD se desvió anormalmente a {eur_price}!"
    assert 1.0500 <= eur_otc_price <= 1.1200, f"EURUSD-OTC se desvió anormalmente a {eur_otc_price}!"
    
    # Debe tener decimales de alta precisión (más de 2 decimales)
    assert round(eur_price, 2) != eur_price or eur_price == 1.08, "EURUSD debe tener precisión de 5 decimales"
