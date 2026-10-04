import pytest
from market_data.market_feed import MultiAssetMarketFeed
from ai_analysis.intelligent_agent import IntelligentTradingAgent
from execution.trading_engine import RealTimeTradingEngine
from trade_journal.journal import TradeJournal

def test_market_feed():
    feed = MultiAssetMarketFeed()
    assets = feed.tick()
    assert len(assets) >= 7
    assert "AAPL" in assets
    assert "BTC" in assets
    assert assets["AAPL"]["price"] > 0

def test_intelligent_agent_evaluation():
    agent = IntelligentTradingAgent()
    feed = MultiAssetMarketFeed()
    assets = feed.tick()
    eval_res = agent.evaluate_asset(assets["AAPL"], {})
    assert "decision" in eval_res
    assert eval_res["decision"] in ["BUY", "SELL", "HOLD"]
    assert len(eval_res["reason_simple"]) > 10

def test_trading_engine_lifecycle():
    engine = RealTimeTradingEngine(initial_balance=10000.0, execution_environment="PAPER")
    assert engine.get_total_equity() == 10000.0
    
    # Run a few steps
    for _ in range(5):
        engine.step()
    
    state = engine.get_full_state()
    assert "financial_summary" in state
    assert "market_radar" in state
    assert len(state["market_radar"]) >= 7
    assert state["financial_summary"]["total_equity"] > 0
