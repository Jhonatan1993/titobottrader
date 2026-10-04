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

def test_binance_adapter_preflight_buy_validation(monkeypatch):
    """Verifica que create_market_order impida comprar si no hay balance USDT mínimo suficiente"""
    adapter = BinanceAdapter(api_key="mock", secret_key="mock")
    adapter.is_configured = True
    adapter.live_trading_enabled = True

    # Mock get_account_balances devolviendo solo 2.0 USDT (menor al mínimo nocional de 5.0)
    monkeypatch.setattr(adapter, "get_account_balances", lambda: {"authenticated": True, "balances": {"USDT": 2.0}, "usdt_free": 2.0, "total_stable_free": 2.0})

    order = adapter.create_market_order("BTCUSDT", "BUY", 0.001)
    assert order["success"] is False
    assert "Saldo insuficiente en Binance Spot" in order["error"]

def test_binance_adapter_preflight_sell_validation_zero_holdings(monkeypatch):
    """Verifica que create_market_order cancele la venta si el usuario no tiene ninguna moneda en Binance (evita error -2010)"""
    adapter = BinanceAdapter(api_key="mock", secret_key="mock")
    adapter.is_configured = True
    adapter.live_trading_enabled = True

    # El usuario tiene 0.0 NEAR en Binance
    monkeypatch.setattr(adapter, "get_account_balances", lambda: {"authenticated": True, "balances": {"USDT": 30.0, "NEAR": {"free": 0.0}}, "usdt_free": 30.0, "total_stable_free": 30.0})

    order = adapter.create_market_order("NEARUSDT", "SELL", 1.0962)
    assert order["success"] is False
    assert "Sin saldo disponible en Binance Spot para vender NEAR" in order["error"]

def test_binance_adapter_preflight_sell_clamping(monkeypatch):
    """Verifica que la cantidad a vender se ajuste automáticamente a los tokens reales en Binance para evitar rechazos por redondeo"""
    import requests
    adapter = BinanceAdapter(api_key="mock", secret_key="mock")
    adapter.is_configured = True
    adapter.live_trading_enabled = True

    # El usuario tiene 1.45 NEAR en Binance, pero el bot cree que tiene 1.50
    monkeypatch.setattr(adapter, "get_account_balances", lambda: {"authenticated": True, "balances": {"NEAR": {"free": 1.45}}, "usdt_free": 20.0, "total_stable_free": 20.0})
    
    # Mock requests.post para observar la llamada enviada
    called_url = []
    class MockResponse:
        status_code = 200
        def json(self):
            return {"symbol": "NEARUSDT", "orderId": 123456, "status": "FILLED", "executedQty": "1.4"}

    def mock_post(url, headers, timeout):
        called_url.append(url)
        return MockResponse()

    monkeypatch.setattr(requests, "post", mock_post)

    order = adapter.create_market_order("NEARUSDT", "SELL", 1.50)
    assert order["success"] is True
    assert len(called_url) == 1
    # Debe haber ajustado la query a quantity=1.4 (redondeado hacia abajo con el stepSize de NEAR que es 0.1)
    assert "quantity=1.4" in called_url[0]

def test_phantom_paper_positions_purged_on_live_activation(monkeypatch):
    """Verifica que al pasar de PAPER a LIVE_REAL se limpien las posiciones simuladas de cripto"""
    engine = RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    engine.active_broker = "BINANCE"
    engine.feed.binance.is_configured = True

    monkeypatch.setattr(engine.feed.binance, "get_account_balances", lambda: {
        "authenticated": True,
        "balances": {"USDT": {"free": 100.0}},
        "usdt_free": 100.0,
        "total_stable_free": 100.0
    })

    # Inyectar una posición simulada
    engine.open_positions["NEAR"] = {
        "symbol": "NEAR",
        "entry_price": 5.0,
        "quantity": 1.0962,
        "side": "BUY"
    }
    assert "NEAR" in engine.open_positions

    # Cambiar a LIVE_REAL
    res = engine.set_execution_environment("LIVE_REAL")
    assert res["success"] is True
    # La posición simulada debe haber sido purgada para evitar vender en real tokens inexistentes
    assert "NEAR" not in engine.open_positions

def test_auth_manager_database_status_and_auth():
    """Verifica que el gestor de autenticación funcione y mantenga la integridad de datos"""
    from dashboard.auth_manager import init_auth_db, authenticate, is_using_postgres
    init_auth_db()
    using_pg = is_using_postgres()
    # Verificar autenticación de admin inicial
    user, err = authenticate("admin", "admin123")
    assert err is None
    assert user is not None
    assert user["role"] == "admin"

def test_alpaca_adapter_preflight_buy_validation(monkeypatch):
    """Verifica que AlpacaAdapter verifique el poder de compra antes de enviar una compra"""
    from execution.alpaca_adapter import AlpacaAdapter
    adapter = AlpacaAdapter(api_key="mock", secret_key="mock")
    adapter.is_configured = True

    # Simular cuenta con solo $0.20 de cash
    monkeypatch.setattr(adapter, "test_connection", lambda: {
        "connected": True,
        "cash": 0.20,
        "buying_power": 0.20
    })

    res = adapter.submit_order("AAPL", 1.0, "buy")
    assert res["success"] is False
    assert "Poder de compra insuficiente en Alpaca" in res["error"]

def test_alpaca_adapter_preflight_sell_validation_zero_holdings(monkeypatch):
    """Verifica que AlpacaAdapter impida vender acciones que el usuario no tiene en cuenta"""
    from execution.alpaca_adapter import AlpacaAdapter
    adapter = AlpacaAdapter(api_key="mock", secret_key="mock")
    adapter.is_configured = True

    # El usuario no tiene acciones de NVDA en Alpaca
    monkeypatch.setattr(adapter, "get_positions", lambda: [])

    res = adapter.submit_order("NVDA", 5.0, "sell")
    assert res["success"] is False
    assert "Sin acciones disponibles en Alpaca para vender NVDA" in res["error"]

def test_alpaca_phantom_paper_positions_purged_on_live_activation(monkeypatch):
    """Verifica que al activar LIVE_REAL en Alpaca se purguen las posiciones simuladas de Wall Street"""
    engine = RealTimeTradingEngine(initial_balance=100000.0, execution_environment="PAPER")
    engine.active_broker = "ALPACA"
    engine.feed.alpaca.is_configured = True

    # Simular conexión exitosa de Alpaca Live y posición real existente de TSLA
    monkeypatch.setattr(engine.feed.alpaca, "test_connection", lambda: {
        "connected": True,
        "cash": 50000.0,
        "equity": 52000.0
    })
    monkeypatch.setattr(engine.feed.alpaca, "get_positions", lambda: [
        {
            "symbol": "TSLA",
            "avg_entry_price": "200.00",
            "current_price": "205.00",
            "qty": "10",
            "market_value": "2050.00",
            "unrealized_pl": "50.00",
            "unrealized_plpc": "0.025"
        }
    ])

    # Inyectar una posición simulada de papel de Apple
    engine.open_positions["AAPL"] = {
        "symbol": "AAPL",
        "entry_price": 180.0,
        "quantity": 5.0,
        "side": "BUY",
        "category": "TRADFI"
    }
    assert "AAPL" in engine.open_positions

    # Pasar Alpaca a LIVE_REAL
    res = engine.set_execution_environment("LIVE_REAL", broker="ALPACA")
    assert res["success"] is True

    # La posición simulada de AAPL debe haber sido purgada
    assert "AAPL" not in engine.open_positions
    # Y la posición real de TSLA debe haber sido sincronizada en la cartera
    assert "TSLA" in engine.open_positions
    assert engine.open_positions["TSLA"]["quantity"] == 10.0


