import pytest
from ai_analysis.regime_detector import MarketRegimeDetector
from ai_analysis.funding_arbitrage import FundingArbitrageScanner
from ai_analysis.news_sentiment_shield import NewsMacroShield
from ai_analysis.intelligent_agent import IntelligentTradingAgent

def test_market_regime_detector():
    detector = MarketRegimeDetector()

    # 1. Bullish Trending Asset
    bull_asset = {
        "price": 100.0,
        "ema20": 98.0,
        "ema50": 95.0,
        "rsi": 58.0,
        "volatility": 0.015,
        "support": 96.0,
        "resistance": 105.0
    }
    bull_res = detector.detect_regime(bull_asset)
    assert bull_res["regime"] == "TRENDING_BULL"
    assert bull_res["allow_buy"] is True
    assert bull_res["kelly_mod"] >= 1.2
    assert bull_res["tp_multiplier"] >= 1.2

    # 2. Bearish Trending Asset
    bear_asset = {
        "price": 90.0,
        "ema20": 92.0,
        "ema50": 96.0,
        "rsi": 38.0,
        "volatility": 0.015,
        "support": 85.0,
        "resistance": 93.0
    }
    bear_res = detector.detect_regime(bear_asset)
    assert bear_res["regime"] == "TRENDING_BEAR"
    assert bear_res["allow_buy"] is False

    # 3. High Volatility / Shock Asset
    shock_asset = {
        "price": 100.0,
        "ema20": 98.0,
        "ema50": 95.0,
        "rsi": 89.0,  # Extreme overbought
        "volatility": 0.045,  # 3x standard
        "support": 90.0,
        "resistance": 110.0
    }
    shock_res = detector.detect_regime(shock_asset)
    assert shock_res["regime"] == "HIGH_VOLATILITY_CHAOTIC"
    assert shock_res["allow_buy"] is False
    assert shock_res["kelly_mod"] <= 0.5

def test_funding_arbitrage_scanner():
    scanner = FundingArbitrageScanner()
    btc_yield = scanner.calculate_yield("BTC", rate_8h=0.0001)
    assert btc_yield["symbol"] == "BTC"
    assert btc_yield["apr_percent"] > 9.0
    assert btc_yield["net_apr_after_fees"] > 0.0
    assert "Delta-Neutral" in btc_yield["risk_type"]

    all_crypto = scanner.scan_all_crypto(["BTC", "ETH", "SOL"])
    assert len(all_crypto) == 3
    # Debe estar ordenado de mayor a menor APR
    assert all_crypto[0]["apr_percent"] >= all_crypto[1]["apr_percent"]

    top = scanner.get_top_opportunity()
    assert "apr_percent" in top
    assert top["apr_percent"] > 0

def test_news_sentiment_macro_shield():
    shield = NewsMacroShield()

    # Shock headline
    bad_news = "SEC lawsuit filed against major crypto exchange with CPI shock"
    bad_res = shield.evaluate_headline(bad_news)
    assert bad_res["status"] == "MACRO_SHOCK_PROTECT"
    assert bad_res["safe_to_buy"] is False
    assert shield.is_macro_environment_safe()["safe"] is False

    # Reset shock for test
    shield.last_shock_time = 0.0
    assert shield.is_macro_environment_safe()["safe"] is True

    # Bullish headline
    good_news = "ETF approved by regulators and rate cut expected by central bank"
    good_res = shield.evaluate_headline(good_news)
    assert good_res["status"] == "MACRO_BULLISH_TAILWIND"
    assert good_res["safe_to_buy"] is True

def test_intelligent_agent_integration_with_new_techniques():
    agent = IntelligentTradingAgent()
    assert hasattr(agent, "regime_detector")
    assert hasattr(agent, "funding_scanner")
    assert hasattr(agent, "sentiment_shield")

    asset = {
        "symbol": "BTC",
        "name": "Bitcoin / USD",
        "price": 65000.0,
        "ema20": 64800.0,
        "ema50": 64000.0,
        "rsi": 55.0,
        "volatility": 0.016,
        "support": 64000.0,
        "resistance": 67000.0,
        "category": "CRYPTO"
    }

    eval_normal = agent.evaluate_asset(asset, {})
    assert "regime" in eval_normal
    assert "regime_tag" in eval_normal

    # Simular shock macro
    agent.sentiment_shield.trigger_shock_event("Cisne negro simulado")
    eval_shock = agent.evaluate_asset(asset, {})
    assert eval_shock["decision"] == "HOLD"
    assert eval_shock["action_type"] == "MACRO_SHIELD_PAUSE"
    assert eval_shock["budget_percent"] == 0.0
