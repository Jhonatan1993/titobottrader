import pytest
from execution.alpaca_adapter import AlpacaAdapter
from execution.binance_adapter import BinanceAdapter
from market_data.market_feed import MultiAssetMarketFeed
from config.broker_config import load_broker_config

def test_broker_config_loading():
    config = load_broker_config()
    assert "operating_mode" in config
    assert "alpaca" in config
    assert "binance" in config

def test_alpaca_unconfigured_behavior():
    adapter = AlpacaAdapter(api_key="", secret_key="")
    conn = adapter.test_connection()
    assert conn["connected"] is False
    assert "no ingresadas" in conn["error"].lower()

def test_binance_public_feed():
    adapter = BinanceAdapter(api_key="", secret_key="")
    conn = adapter.test_connection()
    assert conn["connected"] is True
    assert conn["mode"] == "PUBLIC_FEED"

def test_market_feed_modes():
    feed = MultiAssetMarketFeed()
    assert len(feed.get_all_assets()) >= 8  # AAPL, NVDA, TSLA, MSFT, AMZN, GOOGL, BTC, ETH, SOL
    
    feed.set_mode("BINANCE_CRYPTO")
    assert feed.mode == "BINANCE_CRYPTO"
    
    feed.set_mode("HYBRID")
    assert feed.mode == "HYBRID"
    
    feed.set_mode("SIMULATION")
    assert feed.mode == "SIMULATION"

def test_crypto_assets_in_feed():
    feed = MultiAssetMarketFeed()
    assets = feed.get_all_assets()
    symbols = [a["symbol"] for a in assets]
    assert "BTC" in symbols
    assert "ETH" in symbols
    assert "SOL" in symbols

def test_trading_engine_forces_paper_mode_on_invalid_credentials():
    from execution.trading_engine import RealTimeTradingEngine
    from execution.binance_adapter import BinanceAdapter
    engine = RealTimeTradingEngine(initial_balance=10000.0, execution_environment="PAPER")
    # Inyectar credenciales inválidas a propósito
    engine.feed.binance = BinanceAdapter(api_key="KEY_INVALIDA_DE_PRUEBA", secret_key="SECRET_INVALIDA_DE_PRUEBA")
    
    # Intentar activar MODO REAL con credenciales inválidas debe ser bloqueado inmediatamente
    res = engine.set_execution_environment("LIVE_REAL")
    assert res["success"] is False
    assert engine.execution_environment == "PAPER"
    assert engine.feed.binance.live_trading_enabled is False

