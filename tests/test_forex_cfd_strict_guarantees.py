import time
import pytest
from unittest.mock import patch
from execution.trading_engine import RealTimeTradingEngine

def test_forex_cfd_exclusive_mode():
    """
    GARANTÍA 1: El motor de IQ Option opera exclusivamente en modo Forex CFD.
    Cualquier intento de forzar otros modos se normaliza a IQ_CFD.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    assert engine.active_broker == "IQOPTION"
    assert engine.operating_mode == "IQ_CFD"
    
    # Intentar asignar modos obsoletos
    engine.set_operating_mode("IQ_BINARY")
    assert engine.operating_mode == "IQ_CFD"
    
    engine.set_operating_mode("IQ_HYBRID")
    assert engine.operating_mode == "IQ_CFD"

def test_forex_cfd_buy_execution_attributes():
    """
    GARANTÍA 2: Toda posición abierta en IQ Option se crea como CFD sin tiempo de expiración fija (duration_sec = 0).
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    
    asset = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "category": "FOREX",
        "price": 1.0850,
        "rsi": 55.0,
        "ema20": 1.0852,
        "ema50": 1.0848,
        "volatility": 0.0035,
        "regime": "TRENDING_BULL"
    }
    market_state = {"EURUSD": asset}
    
    with patch.object(engine.agent, "evaluate_asset", return_value={
        "decision": "BUY",
        "confidence": 92,
        "budget_percent": 20.0,
        "reason_simple": "Confluencia técnica alcista",
        "stop_loss": 1.0800,
        "take_profit": 1.0950
    }):
        engine._evaluate_and_trade(market_state)
        
    assert "EURUSD" in engine.open_positions
    pos = engine.open_positions["EURUSD"]
    assert pos["trade_type"] == "CFD"
    assert pos["is_cfd"] is True
    assert pos["duration_sec"] == 0
    assert pos["side"] == "CALL"
    assert pos["stop_loss"] == 1.0800
    assert pos["take_profit"] == 1.0950

def test_forex_cfd_sell_put_execution():
    """
    GARANTÍA 3: Soporte nativo para operaciones bajistas (PUT/VENTA) en Forex CFD con SL por encima y TP por debajo.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    
    asset = {
        "symbol": "GBPUSD",
        "name": "GBP / USD",
        "category": "FOREX",
        "price": 1.2950,
        "rsi": 42.0,
        "ema20": 1.2945,
        "ema50": 1.2955,
        "volatility": 0.0040,
        "regime": "TRENDING_BEAR"
    }
    market_state = {"GBPUSD": asset}
    
    with patch.object(engine.agent, "evaluate_asset", return_value={
        "decision": "SELL",
        "action_type": "VENTA_BAJISTA_CONFIRMADA",
        "confidence": 88,
        "budget_percent": 20.0,
        "reason_simple": "Ruptura bajista confirmada",
        "stop_loss": 1.3000,
        "take_profit": 1.2850
    }):
        engine._evaluate_and_trade(market_state)
        
    assert "GBPUSD" in engine.open_positions
    pos = engine.open_positions["GBPUSD"]
    assert pos["side"] == "PUT"
    assert pos["trade_type"] == "CFD"
    assert pos["is_cfd"] is True
    assert pos["duration_sec"] == 0

def test_forex_cfd_take_profit_exit():
    """
    GARANTÍA 4: Salida automática por Take-Profit garantizado cuando el precio alcanza el objetivo matemático.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    now = time.time()
    
    engine.open_positions["EURUSD"] = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "invested_amount": 2000.0,
        "stop_loss": 1.0800,
        "take_profit": 1.0900,
        "entry_timestamp": now - 30.0,
        "is_cfd": True,
        "trade_type": "CFD",
        "duration_sec": 0
    }
    
    # Simular precio alcanzando Take-Profit (1.0910 >= 1.0900)
    market_state = {
        "EURUSD": {
            "symbol": "EURUSD",
            "name": "EUR / USD",
            "category": "FOREX",
            "price": 1.0910,
            "volatility": 0.0035
        }
    }
    
    init_cash = engine.broker_wallets["IQOPTION"]["cash"]
    engine._evaluate_and_trade(market_state)
    
    assert "EURUSD" not in engine.open_positions
    last_trade = engine.journal.trades[0]
    assert last_trade["pnl"] > 0
    assert "Take-Profit" in last_trade.get("exit_reason", "") or last_trade.get("exit_type") == "SELL_TAKE_PROFIT"
    # El capital + ganancia debe volver directamente al saldo real sin bóvedas
    assert engine.broker_wallets["IQOPTION"]["cash"] > init_cash
    assert engine.broker_wallets["IQOPTION"].get("profit_vault", 0.0) == 0.0

def test_forex_cfd_stop_loss_exit():
    """
    GARANTÍA 5: Salida defensiva estricta por Stop-Loss cuando el precio se mueve en contra, preservando capital.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    now = time.time()
    
    engine.open_positions["EURUSD"] = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "invested_amount": 2000.0,
        "stop_loss": 1.0800,
        "take_profit": 1.0950,
        "entry_timestamp": now - 30.0,
        "is_cfd": True,
        "trade_type": "CFD",
        "duration_sec": 0
    }
    
    # Simular precio cayendo por debajo del Stop-Loss (1.0790 <= 1.0800)
    market_state = {
        "EURUSD": {
            "symbol": "EURUSD",
            "name": "EUR / USD",
            "category": "FOREX",
            "price": 1.0790,
            "volatility": 0.0035
        }
    }
    
    engine._evaluate_and_trade(market_state)
    
    assert "EURUSD" not in engine.open_positions
    last_trade = engine.journal.trades[0]
    assert "Stop-Loss" in last_trade.get("exit_reason", "") or last_trade.get("exit_type") == "SELL_STOP_LOSS"

def test_forex_cfd_break_even_activation():
    """
    GARANTÍA 6: Al avanzar el precio +1R de ganancia, el Stop-Loss se mueve al precio de entrada (CERO RIESGO).
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    now = time.time()
    
    # Entry: 1.0800, SL: 1.0750 (Riesgo R = 0.0050), TP: 1.0925 (+2.5R)
    engine.open_positions["EURUSD"] = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0800,
        "current_price": 1.0800,
        "invested_amount": 2000.0,
        "stop_loss": 1.0750,
        "initial_stop_loss": 1.0750,
        "take_profit": 1.0925,
        "entry_timestamp": now - 15.0,
        "is_cfd": True,
        "trade_type": "CFD",
        "duration_sec": 0
    }
    
    # Precio sube a 1.0855 (+1.1R > 1.0R)
    market_state = {
        "EURUSD": {
            "symbol": "EURUSD",
            "name": "EUR / USD",
            "category": "FOREX",
            "price": 1.0855,
            "volatility": 0.0035
        }
    }
    
    engine._evaluate_and_trade(market_state)
    
    pos = engine.open_positions["EURUSD"]
    assert pos.get("is_break_even") is True
    # El Stop-Loss debe haberse ajustado al precio de entrada
    assert pos["stop_loss"] == 1.0800

def test_forex_cfd_trailing_stop_activation():
    """
    GARANTÍA 7: Al avanzar el precio a +1.5R de ganancia, el Stop-Loss acompaña asegurando al menos +0.5R de ganancia.
    """
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    now = time.time()
    
    # Entry: 1.0800, SL: 1.0750 (R = 0.0050), TP: 1.0950
    engine.open_positions["EURUSD"] = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0800,
        "current_price": 1.0800,
        "invested_amount": 2000.0,
        "stop_loss": 1.0800, # Ya en break-even
        "initial_stop_loss": 1.0750,
        "take_profit": 1.0950,
        "entry_timestamp": now - 15.0,
        "is_break_even": True,
        "is_cfd": True,
        "trade_type": "CFD",
        "duration_sec": 0
    }
    
    # Precio sube a 1.0880 (+1.6R de ganancia)
    market_state = {
        "EURUSD": {
            "symbol": "EURUSD",
            "name": "EUR / USD",
            "category": "FOREX",
            "price": 1.0880,
            "volatility": 0.0035
        }
    }
    
    engine._evaluate_and_trade(market_state)
    
    pos = engine.open_positions["EURUSD"]
    # El trailing SL debe haber subido a entry + 0.5R = 1.0800 + 0.0025 = 1.0825
    expected_trail = round(1.0800 + 0.5 * 0.0050, 4)
    assert pos["stop_loss"] == expected_trail
