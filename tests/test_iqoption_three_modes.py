import time
import pytest
from unittest.mock import patch
from execution.trading_engine import RealTimeTradingEngine

def test_iqoption_operating_mode_selector():
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    assert engine.active_broker == "IQOPTION"
    
    # Probar selector de modos
    engine.set_operating_mode("IQ_BINARY")
    assert engine.operating_mode == "IQ_BINARY"
    
    engine.set_operating_mode("IQ_CFD")
    assert engine.operating_mode == "IQ_CFD"
    
    engine.set_operating_mode("IQ_HYBRID")
    assert engine.operating_mode == "IQ_HYBRID"

def test_iqoption_binary_mode_execution():
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_operating_mode("IQ_BINARY")
    engine._override_timing_gate_for_test = True
    
    asset = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "category": "FOREX",
        "price": 1.0850,
        "rsi": 55.0,
        "volatility": 0.0035,
        "regime": "TRENDING_BULL"
    }
    market_state = {"EURUSD-OTC": asset}
    
    with patch.object(engine.agent, "evaluate_asset", return_value={
        "decision": "BUY",
        "confidence": 92,
        "budget_percent": 20.0,
        "reason_simple": "Señal binaria",
        "stop_loss": 1.0800,
        "take_profit": 1.0900
    }):
        engine._evaluate_and_trade(market_state)
        
    assert "EURUSD-OTC" in engine.open_positions
    pos = engine.open_positions["EURUSD-OTC"]
    assert pos["trade_type"] == "BINARY"
    assert pos["is_cfd"] is False
    assert pos["duration_sec"] == 60

def test_iqoption_cfd_mode_execution():
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_operating_mode("IQ_CFD")
    
    asset = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "category": "FOREX",
        "price": 1.0850,
        "rsi": 55.0,
        "volatility": 0.0035,
        "regime": "RANGING_SIDEWAYS"
    }
    market_state = {"EURUSD-OTC": asset}
    
    with patch.object(engine.agent, "evaluate_asset", return_value={
        "decision": "BUY",
        "confidence": 92,
        "budget_percent": 20.0,
        "reason_simple": "Señal CFD",
        "stop_loss": 1.0800,
        "take_profit": 1.0900
    }):
        engine._evaluate_and_trade(market_state)
        
    assert "EURUSD-OTC" in engine.open_positions
    pos = engine.open_positions["EURUSD-OTC"]
    assert pos["trade_type"] == "CFD"
    assert pos["is_cfd"] is True
    assert pos["duration_sec"] == 0

def test_iqoption_cfd_take_profit_exit():
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_operating_mode("IQ_CFD")
    
    now = time.time()
    engine.open_positions["EURUSD-OTC"] = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "invested_amount": 2000.0,
        "stop_loss": 1.0800,
        "take_profit": 1.0900,
        "entry_timestamp": now - 20.0,
        "is_cfd": True,
        "trade_type": "CFD",
        "duration_sec": 0
    }
    
    # Subida al precio de Take Profit (1.0910 >= 1.0900)
    market_state = {
        "EURUSD-OTC": {
            "symbol": "EURUSD-OTC",
            "name": "EUR / USD (OTC 24/7)",
            "category": "FOREX",
            "price": 1.0910,
            "volatility": 0.0035
        }
    }
    
    init_cash = engine.broker_wallets["IQOPTION"]["cash"]
    engine._evaluate_and_trade(market_state)
    
    assert "EURUSD-OTC" not in engine.open_positions
    last_trade = engine.journal.trades[0]
    assert last_trade["pnl"] > 0
    # Comprobar que NO hay bóveda y que el dinero volvió directamente al efectivo
    assert engine.broker_wallets["IQOPTION"].get("profit_vault", 0.0) == 0.0
    assert engine.broker_wallets["IQOPTION"]["cash"] > init_cash

def test_iqoption_no_vault_on_binary_win():
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_operating_mode("IQ_BINARY")
    
    now = time.time()
    engine.open_positions["EURUSD-OTC"] = {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "broker": "IQOPTION",
        "category": "FOREX",
        "side": "BUY",
        "quantity": 1843.0,
        "entry_price": 1.0850,
        "invested_amount": 2000.0,
        "entry_timestamp": now - 65.0,
        "is_cfd": False,
        "trade_type": "BINARY",
        "duration_sec": 60
    }
    
    asset_win = {"symbol": "EURUSD-OTC", "name": "EUR / USD", "price": 1.0860, "category": "FOREX"}
    init_cash = engine.broker_wallets["IQOPTION"]["cash"]
    engine._execute_sell("EURUSD-OTC", asset_win, {"decision": "SELL_EXPIRATION"})
    
    # Ganancia 88% = +1,760 COP
    # Retorno total = 2000 + 1760 = 3760 COP ingresados directamente al cash
    assert engine.broker_wallets["IQOPTION"]["cash"] == init_cash + 3760.0
    # La bóveda debe permanecer en 0.0 (eliminada)
    assert engine.broker_wallets["IQOPTION"].get("profit_vault", 0.0) == 0.0
    state = engine.get_state()
    assert state["financial_summary"]["profit_vault"] == 0.0
