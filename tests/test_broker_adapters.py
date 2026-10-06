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

def test_iqoption_adapter_demo_and_real_modes():
    from execution.iqoption_adapter import IQOptionAdapter
    # 1. Modo Simulación / Práctica sin credenciales
    adapter = IQOptionAdapter(email="", password="", environment="PAPER")
    conn = adapter.test_connection()
    assert conn["connected"] is True
    assert conn["environment"] == "PAPER"
    assert conn["balance"] == 10000.0

    # 2. Conmutación a PAPER con saldo personalizado
    res_paper = adapter.set_environment("PAPER")
    assert res_paper["success"] is True
    assert adapter.environment == "PAPER"

    # 3. Simulación de orden PAPER
    order = adapter.submit_order("EURUSD", "buy", 50.0)
    assert order["success"] is True
    assert order["environment"] == "PAPER"
    assert "IQ_PAPER_" in order["order_id"]

def test_iqoption_trading_engine_environment_symmetry(monkeypatch):
    from execution.trading_engine import RealTimeTradingEngine
    engine = RealTimeTradingEngine(initial_balance=1000.0, execution_environment="PAPER")
    
    # 1. Verificar presencia de wallet IQ Option aislada
    assert "IQOPTION" in engine.broker_wallets
    iq_wallet = engine.broker_wallets["IQOPTION"]
    assert iq_wallet["environment"] == "PAPER"
    assert iq_wallet["cash"] >= 1000.0

    # 2. Intentar conmutar a LIVE_REAL sin credenciales debe fallar de forma segura
    res_fail = engine.set_execution_environment("LIVE_REAL", broker="IQOPTION")
    assert res_fail["success"] is False
    assert "credenciales" in res_fail["error"].lower()

    # 3. Conectar mock exitoso en IQ Option y conmutar a LIVE_REAL
    monkeypatch.setattr(engine.feed.iqoption, "is_configured", True)
    monkeypatch.setattr(engine.feed.iqoption, "connect", lambda: {
        "connected": True,
        "authenticated": True,
        "environment": "LIVE_REAL",
        "balance": 1542.50,
        "currency": "USD"
    })
    
    res_real = engine.set_execution_environment("LIVE_REAL", broker="IQOPTION")
    assert res_real["success"] is True
    assert res_real["environment"] == "LIVE_REAL"
    assert engine.broker_wallets["IQOPTION"]["environment"] == "LIVE_REAL"
    assert engine.broker_wallets["IQOPTION"]["cash"] == 1542.50

    # 4. Conmutar de vuelta a MODO DEMO / PAPER
    res_paper = engine.set_execution_environment("PAPER", broker="IQOPTION")
    assert res_paper["success"] is True
    assert res_paper["environment"] == "PAPER"
    assert engine.broker_wallets["IQOPTION"]["environment"] == "PAPER"

def test_iqoption_auth_v2_handling(monkeypatch):
    from execution.iqoption_adapter import IQOptionAdapter
    adapter = IQOptionAdapter(email="trader@test.com", password="password123", environment="LIVE_REAL")
    
    # 1. Simular respuesta 401 de credenciales inválidas de auth.iqoption.com
    class MockResp401:
        status_code = 401
        text = '{"code":"invalid_credentials","message":"Wrong credentials"}'
        def json(self):
            return {"code": "invalid_credentials", "message": "Wrong credentials"}
    
    monkeypatch.setattr(adapter.session, "post", lambda url, json, headers, timeout: MockResp401())
    res_fail = adapter.connect()
    assert res_fail["connected"] is False
    assert "Credenciales incorrectas" in res_fail["error"]

    # 2. Simular respuesta 200 exitosa de auth.iqoption.com con perfil
    class MockResp200Auth:
        status_code = 200
        cookies = {"ssid": "mock_ssid_abc123"}
        def json(self):
            return {"code": "success", "ssid": "mock_ssid_abc123"}

    class MockResp200Profile:
        status_code = 200
        def json(self):
            return {
                "result": {
                    "name": "Trader Test",
                    "currency": "USD",
                    "balances": [
                        {"id": 1001, "type": 1, "amount": 850.50},
                        {"id": 1002, "type": 4, "amount": 10000.0}
                    ]
                }
            }

    def mock_post(url, *args, **kwargs):
        return MockResp200Auth()

    def mock_get(url, *args, **kwargs):
        return MockResp200Profile()

    monkeypatch.setattr(adapter.session, "post", mock_post)
    monkeypatch.setattr(adapter.session, "get", mock_get)

    res_ok = adapter.connect()
    assert res_ok["connected"] is True
    assert res_ok["authenticated"] is True
    assert res_ok["real_balance"] == 850.50
    assert res_ok["practice_balance"] == 10000.0
    assert res_ok["balance"] == 850.50
    assert adapter.ssid == "mock_ssid_abc123"

def test_iqoption_direct_ssid_authentication(monkeypatch):
    from execution.iqoption_adapter import IQOptionAdapter
    # Prueba de autenticación directa con Token SSID sin requerir auth.iqoption.com
    adapter = IQOptionAdapter(ssid="valid_user_session_token_12345", environment="LIVE_REAL")
    assert adapter.is_configured is True
    
    class MockProfileResp:
        status_code = 200
        def json(self):
            return {
                "result": {
                    "name": "Trader VIP",
                    "currency": "USD",
                    "balances": [
                        {"id": 2001, "type": 1, "amount": 350.00},
                        {"id": 2002, "type": 4, "amount": 10000.0}
                    ]
                }
            }

    monkeypatch.setattr(adapter.session, "get", lambda url, timeout: MockProfileResp())
    res = adapter.connect()
    assert res["connected"] is True
    assert res["authenticated"] is True
    assert res["method"] == "SSID_DIRECT"
    assert res["real_balance"] == 350.00
    assert res["balance"] == 350.00



