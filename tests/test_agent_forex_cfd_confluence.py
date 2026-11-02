import pytest
from ai_analysis.intelligent_agent import IntelligentTradingAgent

def test_forex_cfd_bullish_confluence_triggers_buy():
    """Verifica que un par Forex con tendencia alcista sólida y RSI óptimo genere BUY con alta confianza."""
    agent = IntelligentTradingAgent()
    
    asset = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "category": "FOREX",
        "price": 1.0850,
        "ema20": 1.0845,
        "ema50": 1.0835,
        "ema200": 1.0800,
        "rsi": 54.0,
        "atr": 0.0006,
        "support": 1.0830,
        "resistance": 1.0870,
        "change_24h": 0.15,
        "volatility": 0.0035
    }
    
    res = agent.evaluate_asset(asset, {})
    assert res["decision"] == "BUY"
    assert res["confidence"] >= 75
    assert res["score"] >= 75
    assert res["take_profit"] > asset["price"]
    assert res["stop_loss"] < asset["price"]
    # Comprobar R:R aproximado 1:2
    risk = asset["price"] - res["stop_loss"]
    reward = res["take_profit"] - asset["price"]
    assert reward >= 1.8 * risk

def test_forex_cfd_bearish_confluence_triggers_sell():
    """Verifica que un par Forex con tendencia bajista estructurada genere SELL con alta confianza."""
    agent = IntelligentTradingAgent()
    
    asset = {
        "symbol": "GBPUSD",
        "name": "GBP / USD",
        "category": "FOREX",
        "price": 1.2920,
        "ema20": 1.2930,
        "ema50": 1.2945,
        "ema200": 1.3000,
        "rsi": 44.0,
        "atr": 0.0008,
        "support": 1.2890,
        "resistance": 1.2940,
        "change_24h": -0.25,
        "volatility": 0.0040
    }
    
    res = agent.evaluate_asset(asset, {})
    assert res["decision"] == "SELL"
    assert res["confidence"] >= 75
    assert res["score"] >= 75
    assert res["take_profit"] < asset["price"]
    assert res["stop_loss"] > asset["price"]
    # Comprobar R:R aproximado 1:2
    risk = res["stop_loss"] - asset["price"]
    reward = asset["price"] - res["take_profit"]
    assert reward >= 1.8 * risk

def test_forex_cfd_neutral_ranging_holds():
    """Verifica que en un mercado lateral plano sin confluencia se mantenga HOLD defensivo."""
    agent = IntelligentTradingAgent()
    
    asset = {
        "symbol": "USDJPY",
        "name": "USD / JPY",
        "category": "FOREX",
        "price": 157.77,
        "ema20": 157.76,
        "ema50": 157.78,
        "ema200": 157.70,
        "rsi": 47.5,
        "atr": 0.12,
        "support": 157.65,
        "resistance": 157.85,
        "change_24h": 0.02,
        "volatility": 0.0045
    }
    
    res = agent.evaluate_asset(asset, {})
    assert res["decision"] == "HOLD"
    assert res["confidence"] < 75

