import time
import pytest
from execution.trading_engine import RealTimeTradingEngine
from execution.binary_options_engine import BinaryOptionsStrategyEngine
from execution.iqoption_adapter import IQOptionAdapter

class DummyIQAdapter:
    def __init__(self):
        self.connected = True
        self.currency = "COP"
        self.real_amount = 25000.0
        self.balance = 25000.0
        self.environment = "PAPER"
        self.orders_executed = []
        self._payout_cache = {
            "EURUSD": 0.88,
            "GBPJPY": 0.85,
            "EURUSD-OTC": 0.90,
            "LOW_PAYOUT": 0.65
        }

    def get_payout(self, symbol: str) -> float:
        return self._payout_cache.get(symbol, 0.85)

    def submit_binary_option(self, symbol: str, direction: str, amount: float, duration_minutes: int = 1):
        order_id = f"BIN_TEST_{int(time.time()*1000)}"
        res = {
            "success": True,
            "order_id": order_id,
            "symbol": symbol,
            "direction": direction,
            "amount": amount,
            "status": "OPENED"
        }
        self.orders_executed.append(res)
        return res

    def submit_order(self, *args, **kwargs):
        res = {"success": True, "order_id": f"FOREX_TEST_{int(time.time()*1000)}"}
        self.orders_executed.append(res)
        return res

    def get_open_positions(self):
        return []

    def get_account_balances(self):
        return {
            "authenticated": True,
            "balance": self.balance,
            "real_balance": self.real_amount,
            "practice_balance": 10000.0,
            "currency": self.currency,
            "environment": self.environment,
            "open_positions": [],
            "positions_synced": True
        }

def test_binary_engine_gatekeeper_single_trade_lock():
    """EVIDENCIA 1: El Gatekeeper de Binarias bloquea tajantemente más de 1 operación simultánea."""
    adapter = DummyIQAdapter()
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=adapter, initial_balance=25000.0)

    # 1. Abrir primera operación
    res1 = engine.execute_binary_option(
        symbol="EURUSD",
        direction="CALL",
        amount=2000.0,
        duration_minutes=1,
        entry_price=1.0850
    )
    assert res1["success"] is True
    assert engine.has_active_position is True
    assert engine.open_position["symbol"] == "EURUSD"
    assert engine.open_position["direction"] == "CALL"

    # 2. Intentar abrir una segunda operación mientras la primera está en curso -> DEBE SER RECHAZADA
    res2 = engine.execute_binary_option(
        symbol="GBPJPY",
        direction="PUT",
        amount=2000.0,
        duration_minutes=1,
        entry_price=211.50
    )
    assert res2["success"] is False
    assert "GATEKEEPER ACTIVO" in res2["error"]
    assert len(adapter.orders_executed) == 1 # Solo 1 orden llegó al broker

def test_binary_engine_payout_filter():
    """EVIDENCIA 2: Filtro matemático de Payout mínimo (>= 80%)."""
    adapter = DummyIQAdapter()
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=adapter, initial_balance=25000.0)

    # Activo con Payout de 65% (inaceptable matemáticamente)
    low_asset = {
        "symbol": "LOW_PAYOUT",
        "price": 1.1000,
        "rsi": 32.0,
        "support": 1.0995,
        "resistance": 1.1200,
        "ema20": 1.1010,
        "ema50": 1.1020
    }
    decision = engine.evaluate_asset(low_asset)
    assert decision["decision"] == "HOLD"
    assert "Payout insuficiente" in decision["reason"]

def test_binary_engine_confluence_call_and_put():
    """EVIDENCIA 3: Disparo estricto de CALL y PUT bajo confluencia analítica A+ (>= 85%)."""
    adapter = DummyIQAdapter()
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=adapter, initial_balance=25000.0)

    # Escenario A+: Rebote alcista en soporte con mecha de absorción y RSI en sobreventa
    call_asset = {
        "symbol": "EURUSD",
        "price": 1.0852,
        "rsi": 38.0,
        "support": 1.0850, # Apenas 0.02% del soporte
        "resistance": 1.0920,
        "ema20": 1.0855,
        "ema50": 1.0860
    }
    # Vela con fuerte mecha inferior (rechazo de caída)
    candles_call = [
        {"open": 1.0858, "high": 1.0860, "low": 1.0845, "close": 1.0852}
    ]
    eval_call = engine.evaluate_asset(call_asset, candles=candles_call)
    assert eval_call["decision"] == "CALL"
    assert eval_call["confidence"] >= 85

    # Escenario A+: Rechazo bajista en resistencia con mecha superior y RSI en sobrecompra
    put_asset = {
        "symbol": "GBPJPY",
        "price": 211.90,
        "rsi": 66.0,
        "support": 210.50,
        "resistance": 212.00, # Apenas 0.05% de la resistencia
        "ema20": 212.05,
        "ema50": 212.20
    }
    # Vela previa intentó perforar resistencia en 212.40 pero fue rechazada hacia abajo (mecha superior dominante)
    candles_put = [
        {"open": 211.95, "high": 212.40, "low": 211.85, "close": 211.90}
    ]
    eval_put = engine.evaluate_asset(put_asset, candles=candles_put)
    assert eval_put["decision"] == "PUT"
    assert eval_put["confidence"] >= 85

def test_binary_engine_resolution_and_slot_release():
    """EVIDENCIA 4: Liquidación automática de opción ganada y liberación del cupo."""
    adapter = DummyIQAdapter()
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=adapter, initial_balance=25000.0)

    now = time.time()
    # Iniciar opción binaria con expiración inmediata (ya cumplida)
    engine.open_position = {
        "id": "BIN_WIN_TEST",
        "symbol": "EURUSD",
        "direction": "CALL",
        "amount": 2000.0,
        "entry_price": 1.0850,
        "payout": 0.88,
        "potential_profit": 1760.0,
        "entry_timestamp": now - 70,
        "expiration_timestamp": now - 10, # Expiró hace 10s
        "duration_minutes": 1,
        "status": "OPEN"
    }

    # Precio actual cerró más arriba (1.0858 > 1.0850) -> WIN
    resolution = engine.check_and_resolve_positions({"EURUSD": 1.0858})
    assert resolution is not None
    assert resolution["result"] == "WIN"
    assert resolution["pnl"] == 1760.0 # +88% de beneficio neto
    assert engine.total_wins == 1
    assert engine.net_profit == 1760.0
    # El cupo debe quedar 100% liberado para la siguiente operación
    assert engine.open_position is None
    assert engine.has_active_position is False

def test_total_isolation_mode_switching():
    """EVIDENCIA 5: Aislamiento total en el motor y conmutador de modo."""
    engine = RealTimeTradingEngine(initial_balance=25000.0)

    # 1. Conmutar a BINARY_OPTIONS
    res_bin = engine.set_iq_mode("BINARY_OPTIONS")
    assert res_bin["success"] is True
    assert engine.iq_mode == "BINARY_OPTIONS"
    assert engine.operating_mode == "IQ_BINARY"

    state_bin = engine.get_state()
    assert state_bin["system_status"]["iq_mode"] == "BINARY_OPTIONS"
    assert state_bin["system_status"]["operating_mode"] == "IQ_BINARY"

    # 2. Conmutar a FOREX_CFD
    res_fx = engine.set_iq_mode("FOREX_CFD")
    assert res_fx["success"] is True
    assert engine.iq_mode == "FOREX_CFD"
    assert engine.operating_mode == "IQ_CFD"

    state_fx = engine.get_state()
    assert state_fx["system_status"]["iq_mode"] == "FOREX_CFD"
    assert state_fx["system_status"]["operating_mode"] == "IQ_CFD"
