import pytest
import os
import json
import tempfile
import time
from ai_analysis.adaptive_learning import AdaptiveLearningEngine

def test_initialization_with_empty_or_missing_file():
    engine = AdaptiveLearningEngine(data_file="data/non_existent_file.json")
    assert engine.total_patterns_learned == 0
    assert engine.portfolio_win_rate == 50.0
    assert engine.portfolio_profit_factor == 1.0
    assert engine.portfolio_expectancy == 0.0
    assert isinstance(engine.mastery_level, str)

def test_recalibration_with_mock_trades():
    mock_trades = [
        # 3 Wins on BTC
        {"symbol": "BTC", "pnl": 10.0, "pnl_percent": 2.0},
        {"symbol": "BTC", "pnl": 15.0, "pnl_percent": 3.0},
        {"symbol": "BTC", "pnl": 8.0, "pnl_percent": 1.6},
        # 2 Losses on ETH (should trigger cooldown)
        {"symbol": "ETH", "pnl": 20.0, "pnl_percent": 4.0},
        {"symbol": "ETH", "pnl": -10.0, "pnl_percent": -2.0},
        {"symbol": "ETH", "pnl": -12.0, "pnl_percent": -2.4}
    ]

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        json.dump(mock_trades, tmp)
        tmp_path = tmp.name

    try:
        engine = AdaptiveLearningEngine(data_file=tmp_path, lookback_trades=10)
        assert engine.total_patterns_learned == 6
        assert "BTC" in engine.asset_stats
        assert "ETH" in engine.asset_stats

        # BTC checks
        btc_stat = engine.asset_stats["BTC"]
        assert btc_stat["win_rate"] == 100.0
        assert btc_stat["wins"] == 3
        assert btc_stat["losses"] == 0
        assert btc_stat["profit_factor"] == 99.0
        assert btc_stat["is_cooling"] is False
        assert btc_stat["safe_kelly_pct"] >= 5.0
        assert btc_stat["volatility_realized"] >= 0.0

        # ETH checks (2 consecutive losses at the end)
        eth_stat = engine.asset_stats["ETH"]
        assert eth_stat["recent_loss_streak"] == 2
        assert eth_stat["is_cooling"] is True
        assert engine.is_asset_in_cooldown("ETH") is True
        assert engine.get_optimal_kelly_budget("ETH") == 0.0

        # Test cooldown clear
        engine.clear_cooldown("ETH")
        assert engine.is_asset_in_cooldown("ETH") is False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_adaptive_sl_tp_calculations():
    engine = AdaptiveLearningEngine(data_file="data/non_existent_file.json")
    price = 60000.0
    base_sl = 0.02
    base_tp = 0.05

    levels = engine.get_adaptive_sl_tp("BTC", base_sl, base_tp, price)
    assert "suggested_sl" in levels
    assert "suggested_tp" in levels
    assert levels["suggested_sl"] < price
    assert levels["suggested_tp"] > price
    assert levels["risk_reward_ratio"] >= 1.8
    assert levels["sl_pct"] > 0
    assert levels["tp_pct"] > levels["sl_pct"]

def test_real_trade_history_calibration():
    # If trades_history.json exists, verify it recalibrates safely
    engine = AdaptiveLearningEngine(data_file="data/trades_history.json")
    summary = engine.get_learning_summary()
    assert "mastery_level" in summary
    assert "patterns_analyzed" in summary
    assert "portfolio_win_rate" in summary
    assert "portfolio_profit_factor" in summary
    assert "asset_stats" in summary
    assert summary["patterns_analyzed"] >= 0
