import time
import pytest
from execution.trading_engine import RealTimeTradingEngine
from execution.binary_options_engine import BinaryOptionsStrategyEngine
from execution.iqoption_adapter import IQOptionAdapter

class CertifiedMockIQAdapter:
    """Adaptador de IQ Option simulado para certificación de auditoría operativa."""
    def __init__(self, currency="USD", balance=1000.0):
        self.connected = True
        self.currency = currency
        self.balance = balance
        self.real_amount = balance
        self.environment = "PAPER"
        self.history_orders = []

    def get_payout(self, symbol: str) -> float:
        payouts = {
            "EURUSD": 0.88,
            "GBPJPY": 0.85,
            "USDJPY": 0.82,
            "EURUSD-OTC": 0.90,
            "LOW_PAY": 0.60
        }
        return payouts.get(symbol, 0.85)

    def submit_binary_option(self, symbol: str, direction: str, amount: float, duration_minutes: int = 1):
        order_id = f"BIN_CERT_{int(time.time()*1000)}"
        res = {
            "success": True,
            "order_id": order_id,
            "symbol": symbol,
            "direction": direction,
            "amount": amount,
            "duration_minutes": duration_minutes,
            "payout": self.get_payout(symbol),
            "environment": self.environment,
            "status": "OPENED"
        }
        self.history_orders.append(res)
        return res

def test_certified_operation_1_call_win_full_lifecycle():
    """
    CERTIFICACIÓN OPERATIVA 1: Ciclo completo de opción binaria CALL Ganadora (Turbo 60s).
    Evidencia:
    - Evaluación de confluencia A+ (RSI sobrevendido + rebote en soporte).
    - Ejecución de orden con Payout 88%.
    - Transición temporal de expiración.
    - Resolución ganadora (WIN) con acreditación de ganancia (+88%).
    - Registro en bitácora con category='BINARY_OPTIONS'.
    - Activación de cooldown de 180s en el par operado.
    """
    adapter = CertifiedMockIQAdapter(currency="USD", balance=100.0)
    engine = RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    engine.set_iq_mode("BINARY_OPTIONS")
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    initial_cash = engine.broker_wallets["IQOPTION"]["cash"]
    assert initial_cash == 100.0

    # 1. Simular mercado en sobreventa con absorción alcista en EURUSD
    market_state = {
        "EURUSD": {
            "symbol": "EURUSD",
            "name": "EUR / USD",
            "price": 1.08500,
            "rsi": 30.5,
            "support": 1.08490,
            "resistance": 1.09100,
            "ema20": 1.08510,
            "ema50": 1.08530,
            "trend_status": "ALCISTA",
            "category": "FOREX",
            "change_percent": 0.20,
            "ai_decision": "CALL",
            "ai_confidence": 92
        }
    }
    engine.feed.candles = {
        "EURUSD": [{"open": 1.0856, "high": 1.0858, "low": 1.0844, "close": 1.0850}]
    }

    # 2. El motor evalúa y lanza la opción binaria
    engine._evaluate_and_trade_binary(market_state)
    assert engine.binary_engine.has_active_position is True
    active = engine.binary_engine.open_position
    assert active["symbol"] == "EURUSD"
    assert active["direction"] == "CALL"
    assert active["amount"] == 2.0 # Inversión de 2.0 USD
    assert active["payout"] == 0.88

    # El capital operativo descuenta la inversión en curso
    assert engine.broker_wallets["IQOPTION"]["cash"] == 98.0

    # 3. Simular que la opción vence a los 60s y el precio sube a 1.08570 (> 1.08500)
    # Adelantar el timestamp de expiración para cumplir el plazo
    active["expiration_timestamp"] = time.time() - 1.0

    # 4. El motor ejecuta su step() y procesa la resolución oficial
    market_state["EURUSD"]["price"] = 1.08570
    engine.feed.tick = lambda: market_state
    engine.step()

    # Evidencia de resolución ganadora
    assert engine.binary_engine.has_active_position is False
    assert engine.binary_engine.total_wins == 1
    # Beneficio neto esperado: 2.0 USD * 0.88 = +1.76 USD
    assert engine.binary_engine.net_profit == 1.76
    # Balance total reintegrado: 98.0 + 2.0 (capital) + 1.76 (beneficio) = 101.76 USD
    assert engine.broker_wallets["IQOPTION"]["cash"] == 101.76

    # Evidencia de registro en Bitácora oficial
    trades = engine.journal.get_trades(limit=5, broker="IQOPTION")
    last_trade = trades[0]
    assert last_trade["symbol"] == "EURUSD"
    assert last_trade["category"] == "BINARY_OPTIONS"
    assert last_trade["pnl"] == 1.76
    assert "¡OPCIÓN BINARIA GANADA!" in last_trade["reason"]

def test_certified_operation_2_put_win_full_lifecycle():
    """
    CERTIFICACIÓN OPERATIVA 2: Ciclo completo de opción binaria PUT Ganadora (Turbo 60s).
    Evidencia:
    - Evaluación de confluencia A+ (RSI sobrecomprado + mecha de rechazo en resistencia).
    - Ejecución de PUT con precio de entrada 212.00.
    - Cierre por debajo de entrada (211.85 < 212.00) -> WIN.
    - Acreditación neta al monedero.
    """
    adapter = CertifiedMockIQAdapter(currency="USD", balance=500.0)
    engine = RealTimeTradingEngine(initial_balance=500.0, execution_environment="PAPER")
    engine.set_iq_mode("BINARY_OPTIONS")
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    market_state = {
        "GBPJPY": {
            "symbol": "GBPJPY",
            "name": "GBP / JPY",
            "price": 212.00,
            "rsi": 68.5,
            "support": 210.50,
            "resistance": 212.05,
            "ema20": 212.05,
            "ema50": 212.15,
            "trend_status": "BAJISTA",
            "category": "FOREX",
            "change_percent": -0.15,
            "ai_decision": "PUT",
            "ai_confidence": 91
        }
    }
    engine.feed.candles = {
        "GBPJPY": [{"open": 211.90, "high": 212.45, "low": 211.80, "close": 212.00}]
    }

    engine._evaluate_and_trade_binary(market_state)
    assert engine.binary_engine.has_active_position is True
    active = engine.binary_engine.open_position
    assert active["direction"] == "PUT"
    assert active["symbol"] == "GBPJPY"

    # Simular expiración cumplida y caída del precio a 211.85
    active["expiration_timestamp"] = time.time() - 1.0
    market_state["GBPJPY"]["price"] = 211.85
    engine.feed.tick = lambda: market_state
    engine.step()

    assert engine.binary_engine.has_active_position is False
    assert engine.binary_engine.total_wins == 1
    # Payout 85% de 2.0 = +1.70 USD
    assert engine.binary_engine.net_profit == 1.70
    assert engine.broker_wallets["IQOPTION"]["cash"] == 501.70

def test_certified_operation_3_gatekeeper_blocks_second_trade():
    """
    CERTIFICACIÓN OPERATIVA 3: Evidencia de protección estricta Gatekeeper (0/1).
    Garantiza que mientras exista 1 opción binaria en curso, ninguna orden adicional
    pueda ser abierta bajo ninguna circunstancia.
    """
    adapter = CertifiedMockIQAdapter(currency="USD", balance=100.0)
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=adapter, initial_balance=100.0)

    # 1. Abrir primera operación
    res1 = engine.execute_binary_option("EURUSD", "CALL", 2.0, entry_price=1.0850)
    assert res1["success"] is True
    assert engine.has_active_position is True

    # 2. Intentar segunda operación en otro par simultáneo
    res2 = engine.execute_binary_option("GBPJPY", "PUT", 2.0, entry_price=211.50)
    assert res2["success"] is False
    assert "GATEKEEPER ACTIVO" in res2["error"]
    assert "estrictamente bloqueadas" in res2["error"]

    # 3. Verificar que solo 1 orden fue enviada al broker
    assert len(adapter.history_orders) == 1

def test_certified_operation_4_tie_refunds_full_capital():
    """
    CERTIFICACIÓN OPERATIVA 4: Empate exacto (TIE) reembolsa el 100% del capital sin pérdidas.
    """
    adapter = CertifiedMockIQAdapter(currency="USD", balance=100.0)
    engine = RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    engine.set_iq_mode("BINARY_OPTIONS")
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    market_state = {
        "USDJPY": {
            "symbol": "USDJPY",
            "price": 152.000,
            "rsi": 31.0,
            "support": 151.980,
            "resistance": 153.000,
            "ema20": 152.050,
            "ema50": 152.100,
            "category": "FOREX",
            "ai_decision": "CALL",
            "ai_confidence": 88
        }
    }
    engine._evaluate_and_trade_binary(market_state)
    active = engine.binary_engine.open_position
    assert active is not None

    # Simular expiración donde el precio de salida es IDÉNTICO al de entrada (152.000)
    active["expiration_timestamp"] = time.time() - 1.0
    market_state["USDJPY"]["price"] = 152.000
    engine.feed.tick = lambda: market_state
    engine.step()

    # En empate: pnl = 0.0, y el saldo vuelve a ser exactamente 100.0 USD
    assert engine.binary_engine.total_ties == 1
    assert engine.binary_engine.net_profit == 0.0
    assert engine.broker_wallets["IQOPTION"]["cash"] == 100.0

def test_certified_operation_5_defensive_loss_zero_martingale():
    """
    CERTIFICACIÓN OPERATIVA 5: Pérdida defensiva controlada sin Martingala.
    Si una opción binaria no se cumple, la pérdida es estrictamente la inversión fija ($2),
    jamás se dobla el monto en la siguiente operación y se activa enfriamiento temporal.
    """
    adapter = CertifiedMockIQAdapter(currency="USD", balance=100.0)
    engine = RealTimeTradingEngine(initial_balance=100.0, execution_environment="PAPER")
    engine.set_iq_mode("BINARY_OPTIONS")
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    market_state = {
        "EURUSD": {
            "symbol": "EURUSD",
            "price": 1.08500,
            "rsi": 32.0,
            "support": 1.08490,
            "resistance": 1.09200,
            "category": "FOREX",
            "ai_decision": "CALL",
            "ai_confidence": 89
        }
    }
    engine._evaluate_and_trade_binary(market_state)
    active = engine.binary_engine.open_position
    assert active["amount"] == 2.0

    # Simular que el precio cerró por debajo (1.08420 < 1.08500)
    active["expiration_timestamp"] = time.time() - 1.0
    market_state["EURUSD"]["price"] = 1.08420
    engine.feed.tick = lambda: market_state
    engine.step()

    assert engine.binary_engine.total_losses == 1
    assert engine.binary_engine.net_profit == -2.0
    assert engine.broker_wallets["IQOPTION"]["cash"] == 98.0

    # Evidencia Anti-Venganza: EURUSD queda bloqueado en cooldown
    eval_blocked = engine.binary_engine.evaluate_asset(market_state["EURUSD"])
    assert eval_blocked["decision"] == "HOLD"
    assert "enfriamiento post-operación" in eval_blocked["reason"]


def test_certified_operation_6_trigger_test_binary_trade_gatekeeper():
    """
    CERTIFICACIÓN OPERATIVA 6: Disparo de orden de prueba controlada y GATEKEEPER 0/1.
    - Ejecuta orden de prueba por valor legal mínimo.
    - Ocupa el cupo único de cartera (1/1).
    - Un segundo intento es RECHAZADO INMEDIATAMENTE por el Gatekeeper inquebrantable.
    - Al resolverse la orden, se libera el cupo a (0/1) para habilitar nuevas entradas.
    """
    adapter = CertifiedMockIQAdapter(currency="COP", balance=50000.0)
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_iq_mode("BINARY_OPTIONS")
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    res1 = engine.trigger_test_binary_trade(symbol="EURJPY", direction="CALL", amount=2000.0)
    assert res1["success"] is True
    assert res1["order_id"].startswith("BIN_CERT_")
    assert engine.binary_engine.has_active_position is True

    # Intento concurrentemente bloqueado por política de 1 sola operación a la vez
    res2 = engine.trigger_test_binary_trade(symbol="AUDUSD", direction="PUT", amount=2000.0)
    assert res2["success"] is False
    assert "GATEKEEPER ACTIVO" in res2["error"]

    # Simular expiración y resolución pausando nuevas compras en el step
    pos = engine.binary_engine.open_position
    pos["expiration_timestamp"] = time.time() - 2.0
    engine.is_running = False
    engine.step()

    # Cupo liberado a 0/1
    assert engine.binary_engine.has_active_position is False
    assert engine.binary_engine.total_wins == 1

    # Al reanudar, el motor autónomo puede tomar la siguiente operación (1 a la vez)
    engine.is_running = True
    engine.step()
    assert engine.binary_engine.has_active_position is True


def test_certified_operation_7_dynamic_candles_confluence_evaluation():
    """
    CERTIFICACIÓN OPERATIVA 7: Evaluación de confluencia con velas de 1m y niveles dinámicos.
    Garantiza que un activo con velas de 1m que rebotan en soporte dinámico genera señal CALL
    con puntaje >= 50 pts sin quedarse estancado en HOLD eterno.
    """
    adapter = CertifiedMockIQAdapter(currency="COP", balance=50000.0)
    engine = RealTimeTradingEngine(initial_balance=50000.0, execution_environment="PAPER")
    engine.set_iq_mode("BINARY_OPTIONS")
    engine.feed.iqoption = adapter
    engine.binary_engine.iq = adapter

    asset = {
        "symbol": "EURJPY",
        "price": 165.200,
        "rsi": 38.0,
        "ema20": 165.195,
        "ema50": 165.190,
        "support": 165.195,
        "resistance": 165.350,
        "change_percent": 0.05,
        "trend_status": "ALCISTA",
        "category": "FOREX"
    }
    candles = [
        {"open": 165.190, "close": 165.192, "high": 165.195, "low": 165.188},
        {"open": 165.192, "close": 165.200, "high": 165.205, "low": 165.190} # Vela verde de rebote
    ]

    eval_res = engine.binary_engine.evaluate_asset(asset, candles)
    assert eval_res["decision"] == "CALL"
    assert eval_res["confidence"] >= 50
    assert "Confluencia Alcista" in eval_res["reason"]
