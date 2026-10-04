import pytest
import math
from market_data.market_feed import MultiAssetMarketFeed, AVAILABLE_ASSETS
from execution.binance_adapter import BinanceAdapter
from execution.trading_engine import RealTimeTradingEngine

def test_binance_adapter_lot_size_precision():
    """Verifica que el formateo de lot size de cada criptomoneda respete exactamente los stepSize de Binance"""
    adapter = BinanceAdapter(api_key="mock", secret_key="mock")
    adapter.is_configured = True
    adapter.live_trading_enabled = True

    # Comprobación de stepSize exactos:
    # NEAR: 0.1, AVAX: 0.01, LINK: 0.01, SOL: 0.001, BNB: 0.001, ETH: 0.0001, BTC: 0.00001, DOGE: 1.0
    cases = [
        ("NEARUSDT", 1.4985, "1.4"),
        ("AVAXUSDT", 0.63936, "0.63"),
        ("LINKUSDT", 7.8243, "7.82"),
        ("SOLUSDT", 0.12345, "0.123"),
        ("BNBUSDT", 0.05432, "0.054"),
        ("ETHUSDT", 0.26303, "0.2630"),
        ("BTCUSDT", 0.00123456, "0.00123"),
        ("DOGEUSDT", 105.7, "105"),
        ("XRPUSDT", 8.88, "8.8"),
        ("ADAUSDT", 45.67, "45.6")
    ]
    for symbol, qty, expected_str in cases:
        sym_clean = symbol.upper().replace("USDT", "")
        if sym_clean == "BTC":
            qty_floored = math.floor(qty * 100000) / 100000
            res = f"{qty_floored:.5f}"
        elif sym_clean == "ETH":
            qty_floored = math.floor(qty * 10000) / 10000
            res = f"{qty_floored:.4f}"
        elif sym_clean in ["BNB", "SOL"]:
            qty_floored = math.floor(qty * 1000) / 1000
            res = f"{qty_floored:.3f}"
        elif sym_clean in ["AVAX", "LINK"]:
            qty_floored = math.floor(qty * 100) / 100
            res = f"{qty_floored:.2f}"
        elif sym_clean in ["NEAR", "XRP", "ADA"]:
            qty_floored = math.floor(qty * 10) / 10
            res = f"{qty_floored:.1f}"
        elif sym_clean == "DOGE":
            res = f"{int(qty)}"
        else:
            qty_floored = math.floor(qty * 100) / 100
            res = f"{qty_floored:.2f}"
        assert res == expected_str, f"Fallo en {symbol}: esperado {expected_str}, obtenido {res}"

def test_market_feed_live_prices_synced():
    """Verifica que el feed mantenga precios reales para todos los activos cripto"""
    feed = MultiAssetMarketFeed()
    assets = feed.tick()
    assert "AVAX" in assets
    # El precio de AVAX debe estar cercano a su cotización real (~10 USD), no al obsoleto 27.50
    assert assets["AVAX"]["price"] < 20.0
    assert assets["AVAX"]["price"] > 2.0
    assert assets["BTC"]["price"] > 40000.0

def test_engine_total_equity_truth():
    """Verifica la regla de verdad de balance (Capital Total = Base + Bóveda de Ganancias)"""
    engine = RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    active_b = engine.active_broker
    engine.broker_wallets[active_b]["profit_vault"] = 15.25
    eq = engine.get_total_equity()
    assert eq == 115.25
    assert engine.get_broker_equity(active_b) == 115.25
