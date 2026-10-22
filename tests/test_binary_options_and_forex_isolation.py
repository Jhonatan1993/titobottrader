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

def test_iqoption_adapter_paper_and_real_binary_payload():
    """EVIDENCIA 6: Verificación de ejecución de Binarias en IQOptionAdapter (Paper y Real WS)."""
    import json
    from unittest.mock import MagicMock, patch

    # 1. MODO PAPER: Debe retornar orden simulada válida inmediatamente
    adapter_paper = IQOptionAdapter(ssid="test_ssid", environment="PAPER")
    adapter_paper.connected = True
    paper_res = adapter_paper.submit_binary_option("EURUSD", "CALL", 2000.0, duration_minutes=1)
    assert paper_res["success"] is True
    assert paper_res["environment"] == "PAPER"
    assert "BIN_PAPER_" in paper_res["order_id"]
    assert paper_res["direction"] == "call"

    # 2. MODO LIVE_REAL: Debe generar el payload WebSocket oficial binary-options.open-option
    adapter_real = IQOptionAdapter(ssid="test_ssid_valid", environment="LIVE_REAL")
    adapter_real.connected = True
    adapter_real.real_amount = 50000.0
    adapter_real.balance = 50000.0
    adapter_real.real_balance_id = 998877

    sent_messages = []
    mock_ws = MagicMock()
    def mock_send(msg):
        sent_messages.append(json.loads(msg))
    mock_ws.send.side_effect = mock_send
    mock_ws.recv.side_effect = [
        '{"name": "profile", "msg": {}}',
        '{"name": "order-placed-temp", "status": 2000, "request_id": "bin_opt_123", "msg": {"id": 555444}}'
    ]

    with patch("websocket.create_connection", return_value=mock_ws):
        # Parchear time.time para capturar request_id consistente
        with patch("time.time", side_effect=[1000.0, 1000.1, 1000.2, 1000.3, 1000.4]):
            res_real = adapter_real._execute_real_binary_ws_order(
                symbol="EURUSD",
                direction="call",
                amount=2000.0,
                duration_minutes=1
            )
            # Encontrar el mensaje oficial enviado
            bin_msg = next((m for m in sent_messages if m.get("name") == "sendMessage" and m.get("msg", {}).get("name") == "binary-options.open-option"), None)
            assert bin_msg is not None, "El mensaje binary-options.open-option no fue transmitido"
            
            body = bin_msg["msg"]["body"]
            assert body["active_id"] == 1 # EURUSD = 1 en IQ Option
            assert body["direction"] == "call"
            assert body["option_type_id"] == 3 # Turbo Binary Option
            assert body["price"] == 2000.0
            assert body["user_balance_id"] == 998877

def test_trading_engine_evaluates_and_executes_binary_option():
    """EVIDENCIA 7: El ciclo de trading de RealTimeTradingEngine ejecuta opciones binarias en modo BINARY_OPTIONS."""
    engine = RealTimeTradingEngine(initial_balance=25000.0, execution_environment="PAPER")
    engine.set_iq_mode("BINARY_OPTIONS")
    assert engine.iq_mode == "BINARY_OPTIONS"

    # Simular mercado con señal fuerte en EURUSD
    market_state = {
        "EURUSD": {
            "symbol": "EURUSD",
            "name": "EUR / USD",
            "price": 1.0850,
            "rsi": 32.0, # Sobreventa profunda
            "support": 1.0849, # En soporte
            "resistance": 1.0920,
            "ema20": 1.0852,
            "ema50": 1.0855,
            "trend_status": "ALCISTA",
            "category": "FOREX",
            "change_percent": 0.15,
            "ai_decision": "CALL",
            "ai_confidence": 90
        }
    }
    # Inyectar velas con mecha de absorción
    engine.feed.candles = {
        "EURUSD": [
            {"open": 1.0858, "high": 1.0860, "low": 1.0842, "close": 1.0850}
        ]
    }

    # Evaluar mercado en modo binarias
    engine._evaluate_and_trade_binary(market_state)

    # Debe haberse disparado la opción binaria
    assert engine.binary_engine.has_active_position is True
    pos = engine.binary_engine.open_position
    assert pos["symbol"] == "EURUSD"
    assert pos["direction"] == "CALL"
    assert pos["amount"] > 0
    assert pos["payout"] >= 0.80

    # Estado del sistema debe reportar la opción binaria activa
    state = engine.get_state()
    assert state["binary_options"]["has_active_trade"] is True
    assert state["binary_options"]["active_trade"]["symbol"] == "EURUSD"

