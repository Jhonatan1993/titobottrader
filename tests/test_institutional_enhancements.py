import pytest
import time
import pandas as pd
from strategy.smc_engine import SMCEngine
from ai_analysis.economic_calendar import EconomicCalendarFilter
from risk_management.soros_manager import SorosRiskManager
from execution.binary_options_engine import BinaryOptionsStrategyEngine

def generate_mock_candles(count: int = 50):
    candles = []
    base_time = int(time.time()) - (count * 60)
    price = 1.0850
    for i in range(count):
        c_open = price
        c_close = price + (0.0003 if i % 2 == 0 else -0.0002)
        c_high = max(c_open, c_close) + 0.0002
        c_low = min(c_open, c_close) - 0.0002
        candles.append({
            "from": base_time + (i * 60),
            "open": c_open,
            "max": c_high,
            "min": c_low,
            "close": c_close,
            "volume": 100
        })
        price = c_close
    return candles

def test_smc_engine_prepare_and_analyze():
    candles = generate_mock_candles(60)
    df = SMCEngine.prepare_indicators(candles)
    assert not df.empty
    assert "ema_fast" in df.columns
    assert "rsi" in df.columns
    assert "bull_fvg" in df.columns
    assert "bear_fvg" in df.columns

    res = SMCEngine.analyze(candles, asset="EURUSD")
    assert "decision" in res
    assert res["decision"] in ["CALL", "PUT", "HOLD"]
    assert "confidence" in res
    assert "reason" in res

def test_economic_calendar_otc_bypass():
    cal = EconomicCalendarFilter()
    safe, reason = cal.is_safe_to_trade("EURUSD-OTC")
    assert safe is True
    assert "OTC" in reason

def test_soros_risk_manager_progression():
    soros = SorosRiskManager(base_stake=10.0, soros_enabled=True, max_soros_level=1)
    
    # Base stake inicial
    assert soros.calculate_stake() == 10.0
    
    # Tras ganar 8.50, el siguiente stake debe ser 10 + 8.50 = 18.50
    res_win = soros.register_trade_result(profit=8.50, invested=10.0)
    assert res_win["outcome"] == "WIN"
    assert soros.soros_step == 1
    assert soros.calculate_stake() == 18.50

    # Tras completar el nivel 1 o perder, debe volver a base
    res_next = soros.register_trade_result(profit=-18.50, invested=18.50)
    assert res_next["outcome"] == "LOSS"
    assert soros.soros_step == 0
    assert soros.calculate_stake() == 10.0

def test_currency_exposure_filter():
    soros = SorosRiskManager()
    assert soros.check_currency_exposure("EURUSD", "CALL") is True
    soros.register_currency_exposure("EURUSD", "CALL")
    # Misma divisa y dirección en el mismo minuto debe ser bloqueada
    assert soros.check_currency_exposure("EURJPY", "CALL") is False
    # Dirección opuesta en divisa distinta es permitida
    assert soros.check_currency_exposure("GBPJPY", "PUT") is True

def test_binary_engine_evaluation():
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=None)
    mock_asset = {
        "symbol": "EURUSD",
        "price": 1.0850,
        "rsi": 50.0,
        "ema20": 1.0845,
        "ema50": 1.0840
    }
    candles = generate_mock_candles(50)
    eval_res = engine.evaluate_asset(mock_asset, candles)
    assert "decision" in eval_res
    assert eval_res["decision"] in ["CALL", "PUT", "HOLD"]
    assert "confidence" in eval_res

    status = engine.get_status()
    assert "smc_engine" in status
    assert "soros_enabled" in status
    assert "economic_calendar" in status
