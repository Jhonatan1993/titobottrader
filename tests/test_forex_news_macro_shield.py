import pytest
import time
from ai_analysis.news_sentiment_shield import NewsMacroShield
from ai_analysis.intelligent_agent import IntelligentTradingAgent

def test_news_macro_shield_forex_seeds_clean_of_crypto():
    """Garantiza que las semillas iniciales son 100% Forex y macroeconomía global, sin vestigios cripto."""
    shield = NewsMacroShield(enable_live_stream=False)
    assert len(shield.headlines_feed) >= 5
    
    crypto_terms = ["bitcoin", "ethereum", "crypto", "coindesk", "btc", "eth", "solana", "binance"]
    for entry in shield.headlines_feed:
        headline_lower = entry["headline"].lower()
        source_lower = entry["source"].lower()
        for term in crypto_terms:
            assert term not in headline_lower, f"Término cripto '{term}' encontrado en titular: {entry['headline']}"
            assert term not in source_lower, f"Fuente cripto '{term}' encontrada en fuente: {entry['source']}"

def test_crypto_news_do_not_trigger_forex_shock():
    """Garantiza que noticias sobre criptomonedas no disparan shock ni bloquean la operativa de Forex."""
    shield = NewsMacroShield(enable_live_stream=False)
    
    crypto_headlines = [
        "Bitcoin plunges 15% following exchange insolvency rumors",
        "Major hack exploit drains $100M from DeFi crypto protocol",
        "SEC files lawsuit against new crypto token offering",
        "Ethereum ETF approved as crypto adoption expands"
    ]
    
    for h in crypto_headlines:
        res = shield.evaluate_headline(h)
        # No debe activar pánico o shock macro en Forex
        assert res["status"] != "MACRO_SHOCK_PROTECT", f"Noticia cripto '{h}' disparó shock en Forex!"
        assert res["safe_to_buy"] is True, f"Noticia cripto '{h}' bloqueó compras en Forex!"

def test_real_forex_and_central_bank_shocks_trigger_protection():
    """Garantiza que eventos reales de alta volatilidad cambiaria sí activan la protección defensiva."""
    shield = NewsMacroShield(enable_live_stream=False)
    
    forex_shock_headlines = [
        "Central bank emergency rate hike announced amid currency crisis",
        "Government orders aggressive forex intervention as currency devaluates",
        "Sovereign default declared following severe debt crisis",
        "Major war escalation sparks widespread liquidity freeze"
    ]
    
    for h in forex_shock_headlines:
        res = shield.evaluate_headline(h)
        assert res["status"] == "MACRO_SHOCK_PROTECT", f"Titular de shock Forex '{h}' no activó protección!"
        assert res["safe_to_buy"] is False
        assert res["sentiment_score"] <= -0.75

def test_forex_bullish_and_stability_signals():
    """Garantiza que titulares de estabilidad y viento a favor macroeconómico generan puntuación positiva."""
    shield = NewsMacroShield(enable_live_stream=False)
    
    stable_headlines = [
        "Federal Reserve rate cut expected as inflation slows to target",
        "European Central Bank confirms soft landing confirmed and stable interest rates",
        "Global trade surplus and GDP growth beats institutional forecasts"
    ]
    
    for h in stable_headlines:
        res = shield.evaluate_headline(h)
        assert res["status"] in ["MACRO_BULLISH_TAILWIND", "MACRO_STABLE_NEUTRAL"]
        assert res["safe_to_buy"] is True
        assert res["sentiment_score"] > 0.0

def test_macro_shield_cooldown_duration():
    """Garantiza que la duración de pausa preventiva tras un shock cambiario es de 120 segundos (no 300s)."""
    shield = NewsMacroShield(enable_live_stream=False)
    assert shield.shock_cooldown_sec == 120.0
    
    # Al inicio sin shock
    check_init = shield.is_macro_environment_safe(symbol="EURUSD")
    assert check_init["safe"] is True
    assert check_init["status"] == "MACRO_STABLE"
    
    # Disparar shock
    shield.trigger_shock_event("Intervención cambiaria de emergencia")
    check_shock = shield.is_macro_environment_safe(symbol="EURUSD")
    assert check_shock["safe"] is False
    assert check_shock["status"] == "MACRO_SHOCK_COOLDOWN"
    assert 0 < check_shock["remaining_sec"] <= 120

def test_intelligent_agent_respects_macro_shield_for_forex():
    """Garantiza que el agente inteligente aplica la pausa macro a activos de Forex ante shock real."""
    agent = IntelligentTradingAgent()
    agent.sentiment_shield.enable_live_stream = False
    
    forex_asset = {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "price": 1.0850,
        "ema20": 1.0830,
        "ema50": 1.0810,
        "rsi": 54.0,
        "volatility": 0.0035,
        "support": 1.0800,
        "resistance": 1.0920,
        "category": "FOREX"
    }
    
    # 1. En condiciones normales
    agent.sentiment_shield.last_shock_time = 0.0
    eval_normal = agent.evaluate_asset(forex_asset, {})
    assert eval_normal["action_type"] != "MACRO_SHIELD_PAUSE"
    
    # 2. Con shock activado
    agent.sentiment_shield.trigger_shock_event("Shock cambiario global")
    eval_shock = agent.evaluate_asset(forex_asset, {})
    assert eval_shock["decision"] == "HOLD"
    assert eval_shock["action_type"] == "MACRO_SHIELD_PAUSE"
    assert eval_shock["budget_percent"] == 0.0
