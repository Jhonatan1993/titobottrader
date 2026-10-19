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
    
    # El precio debe mantenerse dentro de un rango realista (+/- 10% de 1.0850)
    assert 1.0000 <= eur_price <= 1.2500, f"EURUSD se desvió anormalmente a {eur_price}!"
    assert 1.0000 <= eur_otc_price <= 1.2500, f"EURUSD-OTC se desvió anormalmente a {eur_otc_price}!"
    
    # Debe tener decimales de alta precisión (más de 2 decimales)
    assert round(eur_price, 2) != eur_price or eur_price == 1.08, "EURUSD debe tener precisión de 5 decimales"

def test_binary_candle_timing_gate_blocks_mid_candle():
    """
    GARANTÍA 6: El filtro de tiempo (Candle Timing Gate) debe bloquear la entrada
    en opciones binarias si el segundo actual está a mitad de vela (ej. segundo :25).
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    
    # Simular tiempo a mitad de vela: segundo 25 (60 * 1000 + 25 = 60025, 60025 % 60 = 25)
    fixed_time = 60000 + 25
    
    asset = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "category": "FOREX",
        "price": 1.0850,
        "rsi": 50.0,
        "ema20": 1.0852,
        "ema50": 1.0848,
        "support": 1.0830,
        "resistance": 1.0920,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    }
    market_state = {"EURUSD-OTC": asset}
    
    with patch("time.time", return_value=float(fixed_time)):
        with patch.object(engine.agent, "evaluate_asset", return_value={
            "decision": "BUY",
            "confidence": 92,
            "budget_percent": 20.0,
            "reason_simple": "Confluencia técnica óptima",
            "stop_loss": 1.0800,
            "take_profit": 1.0900
        }):
            engine._evaluate_and_trade(market_state)
            
    # La posición NO debe abrirse porque a segundo :25 el Timing Gate está CERRADO
    assert "EURUSD-OTC" not in engine.open_positions, "El Timing Gate debió bloquear la compra a mitad de vela (:25)!"

def test_binary_candle_timing_gate_allows_boundary():
    """
    GARANTÍA 7: El filtro de tiempo debe PERMITIR la entrada cuando el segundo
    está en la ventana de transición (:56 a :59, o :00 a :04), garantizando vela completa.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    
    # Simular tiempo en segundo 58 (transición de vela)
    fixed_time = 60000 + 58
    
    asset = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "category": "FOREX",
        "price": 1.0850,
        "rsi": 50.0,
        "ema20": 1.0852,
        "ema50": 1.0848,
        "support": 1.0830,
        "resistance": 1.0920,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    }
    market_state = {"EURUSD-OTC": asset}
    
    with patch("time.time", return_value=float(fixed_time)):
        with patch.object(engine.agent, "evaluate_asset", return_value={
            "decision": "BUY",
            "confidence": 92,
            "budget_percent": 20.0,
            "reason_simple": "Confluencia técnica óptima",
            "stop_loss": 1.0800,
            "take_profit": 1.0900
        }):
            engine._evaluate_and_trade(market_state)
            
    # La posición SÍ debe abrirse porque en segundo :58 el Timing Gate está ABIERTO
    assert "EURUSD-OTC" in engine.open_positions, "El Timing Gate debió permitir la compra en la frontera de vela (:58)!"
    assert engine.open_positions["EURUSD-OTC"]["duration_sec"] == 60

def test_binary_payout_filter_rejects_sub_80_percent():
    """
    GARANTÍA 8: Si el payout de IQ Option para un par cae por debajo del 80% (ej. 72%),
    el motor cuantitativo debe descartar el par para proteger la expectativa matemática.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    engine._override_timing_gate_for_test = True
    
    asset = {
        "symbol": "GBPUSD-OTC",
        "name": "GBP / USD (OTC 24/7)",
        "category": "FOREX",
        "price": 1.2950,
        "rsi": 50.0,
        "ema20": 1.2955,
        "ema50": 1.2945,
        "support": 1.2900,
        "resistance": 1.3050,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    }
    market_state = {"GBPUSD-OTC": asset}
    
    # Simular payout bajo (72% < 80%)
    with patch.object(engine.feed.iqoption, "get_payout", return_value=0.72):
        with patch.object(engine.agent, "evaluate_asset", return_value={
            "decision": "BUY",
            "confidence": 95,
            "budget_percent": 20.0,
            "reason_simple": "Confluencia alta",
            "stop_loss": 1.2900,
            "take_profit": 1.3000
        }):
            engine._evaluate_and_trade(market_state)
            
    # No debe operar por payout insuficiente
    assert "GBPUSD-OTC" not in engine.open_positions, "El filtro de Payout debió rechazar el par con payout 72%!"

def test_binary_payout_filter_allows_above_80_percent():
    """
    GARANTÍA 9: Si el payout es >= 80% (ej. 88%), el activo es aprobado para ejecución.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    engine._override_timing_gate_for_test = True
    
    asset = {
        "symbol": "USDJPY-OTC",
        "name": "USD / JPY (OTC 24/7)",
        "category": "FOREX",
        "price": 150.25,
        "rsi": 52.0,
        "ema20": 150.30,
        "ema50": 150.15,
        "support": 149.80,
        "resistance": 151.00,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    }
    market_state = {"USDJPY-OTC": asset}
    
    with patch.object(engine.feed.iqoption, "get_payout", return_value=0.88):
        with patch.object(engine.agent, "evaluate_asset", return_value={
            "decision": "BUY",
            "confidence": 95,
            "budget_percent": 20.0,
            "reason_simple": "Confluencia alta",
            "stop_loss": 149.80,
            "take_profit": 151.00
        }):
            engine._evaluate_and_trade(market_state)
            
    assert "USDJPY-OTC" in engine.open_positions, "El activo con payout de 88% debió ser aprobado!"

def test_iqoption_category_lockdown_no_crypto_no_stock():
    """
    GARANTÍA 10: Bloqueo estricto de categoría en IQ Option:
    Aunque BTC o NVDA tengan señal de compra con 99% de confianza,
    IQ Option NUNCA los compra (solo FOREX, OPTIONS, CFD).
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    engine._override_timing_gate_for_test = True
    
    # Desactivar temporalmente Binance y Alpaca para probar únicamente IQ Option
    engine.broker_wallets["BINANCE"]["is_running"] = False
    engine.broker_wallets["ALPACA"]["is_running"] = False
    
    market_state = {
        "BTC": {"symbol": "BTC", "name": "Bitcoin", "category": "CRYPTO", "price": 65000.0},
        "NVDA": {"symbol": "NVDA", "name": "NVIDIA", "category": "TRADFI_STOCK", "price": 125.0}
    }
    
    with patch.object(engine.agent, "evaluate_asset", return_value={
        "decision": "BUY",
        "confidence": 99,
        "budget_percent": 20.0,
        "reason_simple": "Super señal",
        "stop_loss": 60000.0,
        "take_profit": 70000.0
    }):
        engine._evaluate_and_trade(market_state)
        
    assert "BTC" not in engine.open_positions, "IQ Option jamás debe abrir CRYPTO!"
    assert "NVDA" not in engine.open_positions, "IQ Option jamás debe abrir TRADFI_STOCK!"

def test_alpaca_and_binance_not_affected_by_binary_timing_gate():
    """
    GARANTÍA 11: Independencia multibróker: Las acciones de Alpaca y Cripto de Binance
    pueden operar en cualquier segundo (ej. :25) y NO están sujetas al Timing Gate de binarias.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.broker_wallets["ALPACA"]["environment"] = "PAPER"
    engine.agent.learner.clear_cooldown()
    
    # Segundo :25 (Timing Gate cerrado para binarias)
    fixed_time = 60000 + 25
    
    market_state = {
        "BTC": {"symbol": "BTC", "name": "Bitcoin", "category": "CRYPTO", "price": 65000.0, "binance_pair": "BTCUSDT"},
        "AAPL": {"symbol": "AAPL", "name": "Apple", "category": "TRADFI_STOCK", "price": 230.0}
    }
    
    with patch("time.time", return_value=float(fixed_time)):
        with patch.object(engine.agent, "evaluate_asset", return_value={
            "decision": "BUY",
            "confidence": 90,
            "budget_percent": 20.0,
            "reason_simple": "Compra Spot válida",
            "stop_loss": 60000.0,
            "take_profit": 70000.0
        }):
            engine._evaluate_and_trade(market_state)
            
    # BTC (Binance) y AAPL (Alpaca) deben operar normalmente a segundo :25
    assert "BTC" in engine.open_positions, "Binance Spot debió operar sin bloqueo de timing gate!"
    assert "AAPL" in engine.open_positions, "Alpaca TradFi debió operar sin bloqueo de timing gate!"

def test_binary_option_dynamic_payout_calculation():
    """
    GARANTÍA 12: Si un activo paga 91% en IQ Option, el PnL calculado debe ser
    exactamente el 91% de la inversión en caso de victoria.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    
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
    
    with patch.object(engine.feed.iqoption, "get_payout", return_value=0.91):
        engine._execute_sell("EURUSD-OTC", asset_win, {"decision": "SELL_EXPIRATION"})
        
    last_trade = engine.journal.trades[0]
    # Inversión 2000 COP * 0.91 = 1820 COP
    assert last_trade["pnl"] == 1820.0, f"Ganancia esperada +1,820 COP (+91%), pero dio {last_trade['pnl']}"
    assert last_trade["pnl_percent"] == 91.0

def test_binary_option_put_execution_and_win():
    """
    GARANTÍA 13: El motor debe permitir operaciones de BAJA (PUT) en IQ Option
    cuando hay confluencia técnica bajista y liquidarlas con +88% si el precio cae.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    engine._override_timing_gate_for_test = True
    
    asset = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "category": "FOREX",
        "price": 1.0850,
        "rsi": 45.0,
        "ema20": 1.0845,
        "ema50": 1.0855,
        "support": 1.0750,
        "resistance": 1.0860,
        "volatility": 0.0035,
        "trend_bias": -0.0001
    }
    market_state = {"EURUSD-OTC": asset}
    
    # Simular señal bajista SELL / PUT
    with patch.object(engine.agent, "evaluate_asset", return_value={
        "decision": "SELL",
        "action_type": "VENTA_BAJISTA_CONFIRMADA",
        "confidence": 92,
        "budget_percent": 20.0,
        "reason_simple": "Confluencia bajista fuerte",
        "stop_loss": 1.0900,
        "take_profit": 1.0800
    }):
        engine._evaluate_and_trade(market_state)
        
    assert "EURUSD-OTC" in engine.open_positions, "La opción PUT debió abrirse!"
    pos = engine.open_positions["EURUSD-OTC"]
    assert pos["side"] == "PUT", f"La posición debió tener lado PUT pero tiene {pos['side']}"
    
    # Simular expiración donde el precio cayó a 1.0840 (Ganancia para el PUT)
    asset_expired = {"symbol": "EURUSD-OTC", "name": "EUR / USD", "price": 1.0840, "category": "FOREX"}
    engine._execute_sell("EURUSD-OTC", asset_expired, {"decision": "SELL_EXPIRATION"})
    
    last_trade = engine.journal.trades[0]
    assert last_trade["pnl"] > 0, f"El PUT con precio menor debió ser ganador (+88%), pero dio {last_trade['pnl']}"
    assert last_trade["pnl_percent"] == 88.0

def test_risk_manager_isolated_daily_loss_per_broker():
    """
    GARANTÍA 14: Una pérdida en IQ Option (en pesos COP) NO debe bloquear
    a Alpaca o Binance (en USD) por choque de divisas en el RiskManager.
    """
    from risk_management.risk_manager import RiskManager
    rm = RiskManager(initial_balance=14.87, risk_per_trade=0.01, max_daily_loss=0.05, max_open_trades=5)
    
    # Registrar una pérdida de 2000 COP en IQ Option
    rm.register_trade_close(pnl=-2000.0, symbol="EURUSD-OTC", broker_id="IQOPTION")
    
    # La pérdida de IQ Option está aislada en IQ Option
    assert rm.daily_losses.get("IQOPTION") == 2000.0
    # Binance no tiene pérdidas
    assert rm.daily_losses.get("BINANCE", 0.0) == 0.0
    
    # Binance debe poder abrir su trade normalmente sin ser bloqueado por los 2000 COP de IQ Option
    can_binance_open = rm.can_open_trade(risk_amount=0.12, current_equity=14.87, broker_id="BINANCE", broker_initial_balance=14.87)
    assert can_binance_open is True, "Binance no debió ser bloqueado por las pérdidas en COP de IQ Option!"


