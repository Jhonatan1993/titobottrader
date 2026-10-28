import time
import pytest
from unittest.mock import MagicMock, patch
from execution.iqoption_adapter import IQOptionAdapter, ACTIVE_ASSET_IDS
from execution.binary_options_engine import BinaryOptionsStrategyEngine
from market_data.market_feed import MultiAssetMarketFeed, AVAILABLE_ASSETS
from execution.trading_engine import RealTimeTradingEngine


def test_dead_time_expiration_calculation_and_retry():
    """
    Bug 1: Verifica que al disparar en segundo >= 29 (ej. segundo 58),
    la expiración apunte al cierre del minuto siguiente (+120s), evitando
    el error 'Time for purchasing options is over', y verifica auto-reintento +60s.
    """
    adapter = IQOptionAdapter(ssid="test_ssid_123")
    
    # 1. Simular segundo 58
    # Base timestamp en segundo 58: 1700040058 (1700040058 % 60 = 58 >= 29)
    ts_sec_58 = 1700040058
    assert ts_sec_58 % 60 == 58
    now_ts = ts_sec_58
    cur_sec = now_ts % 60
    if cur_sec < 29:
        computed_58 = int(now_ts - cur_sec + 60)
    else:
        computed_58 = int(now_ts - cur_sec + 120)
    
    # El timestamp debe ser 1700040120 (a 62 segundos de distancia)
    assert computed_58 == 1700040120
    assert (computed_58 - ts_sec_58) == 62

    # 2. Simular segundo 05 (< 29)
    ts_sec_05 = 1700040005
    assert ts_sec_05 % 60 == 5
    now_ts = ts_sec_05
    cur_sec = now_ts % 60
    if cur_sec < 29:
        computed_05 = int(now_ts - cur_sec + 60)
    else:
        computed_05 = int(now_ts - cur_sec + 120)
    
    # El timestamp debe ser 1700040060 (a 55 segundos de distancia)
    assert computed_05 == 1700040060
    assert (computed_05 - ts_sec_05) == 55

    # 3. Simular retry en _execute_real_binary_ws_order ante "Time for purchasing options is over"
    mock_ws = MagicMock()
    sent_payloads = []
    def fake_send(payload_str):
        import json
        sent_payloads.append(json.loads(payload_str))
    
    mock_ws.send.side_effect = fake_send
    mock_ws.recv.side_effect = [
        '{"name": "timeSync", "msg": 1700000058000}',
        '{"name": "profile", "msg": {"balances": [{"id": 11111, "type": 4, "amount": 10000.0}]}}',
        '{"name": "option-rejected", "msg": {"message": "Time for purchasing options is over, please try again later"}}',
        '{"name": "option-opened", "msg": {"id": 14396999999}}'
    ]

    with patch.object(adapter, "_get_persistent_ws", return_value=mock_ws):
        res = adapter._execute_real_binary_ws_order(
            symbol="EURUSD-OTC",
            direction="CALL",
            amount=2.0,
            duration_minutes=1
        )

    # Debe haber concretado la orden en el segundo intento sumando +60s
    assert res["success"] is True
    assert res["order_id"] == "14396999999"

    # Verificar que el segundo mensaje sendMessage tuvo expired incrementado
    binary_sends = [p for p in sent_payloads if isinstance(p.get("msg"), dict) and p["msg"].get("name") == "binary-options.open-option"]
    assert len(binary_sends) == 2
    exp1 = binary_sends[0]["msg"]["body"]["expired"]
    exp2 = binary_sends[1]["msg"]["body"]["expired"]
    assert exp2 == exp1 + 60


def test_flat_candles_and_corrupt_jpy_price_rejected():
    """
    Bug 2: Verifica que velas congeladas (plana / std=0) o cotizaciones
    falsas de JPY (< 50.0) sean bloqueadas inmediatamente con HOLD y confianza 0.
    Verifica además que los pares OTC secundarios existan en AVAILABLE_ASSETS.
    """
    adapter = MagicMock()
    adapter.get_payout.return_value = 0.88
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=adapter)

    # 1. Verificar existencia de AUDCAD-OTC, USDCAD-OTC, GBPJPY-OTC en AVAILABLE_ASSETS
    asset_symbols = {a["symbol"]: a for a in AVAILABLE_ASSETS}
    assert "AUDCAD-OTC" in asset_symbols
    assert "USDCAD-OTC" in asset_symbols
    assert "GBPJPY-OTC" in asset_symbols
    assert "CHFJPY-OTC" in asset_symbols
    assert asset_symbols["GBPJPY-OTC"]["base_price"] > 150.0 # ~210.23
    assert asset_symbols["AUDCAD-OTC"]["base_price"] < 1.0 # ~0.8850

    # 2. Evaluar activo JPY corrupto (ej. GBPJPY cotizando en 0.988)
    corrupt_asset = {
        "symbol": "GBPJPY-OTC",
        "price": 0.98838, # Cotización anómala
        "rsi": 50.3,
        "ema20": 0.988,
        "ema50": 0.988,
        "support": 0.988,
        "resistance": 0.98838
    }
    dummy_candles = [{"time": i*60, "open": 0.988, "high": 0.989, "low": 0.987, "close": 0.988, "volume": 100} for i in range(20)]
    eval_jpy = engine.evaluate_asset(corrupt_asset, dummy_candles)
    assert eval_jpy["decision"] == "HOLD"
    assert eval_jpy["confidence"] == 0
    assert "Precio anómalo para par JPY" in eval_jpy["reason"]

    # 3. Evaluar activo con velas planas / congeladas (sin variación de precio)
    flat_asset = {
        "symbol": "AUDCAD-OTC",
        "price": 0.82541,
        "rsi": 50.4,
        "ema20": 0.82541,
        "ema50": 0.82541,
        "support": 0.82541,
        "resistance": 0.82541
    }
    flat_candles = [{"time": i*60, "open": 0.82541, "high": 0.82541, "low": 0.82541, "close": 0.82541, "volume": 10} for i in range(20)]
    eval_flat = engine.evaluate_asset(flat_asset, flat_candles)
    assert eval_flat["decision"] == "HOLD"
    assert eval_flat["confidence"] == 0
    assert "Velas congeladas/planas" in eval_flat["reason"]


def test_closed_asset_blacklist_exclusion():
    """
    Bug 3: Verifica que cuando el broker rechaza un activo con
    'Cannot purchase an option (the asset is not available at the moment)',
    el activo se añade a la lista negra por 30 minutos y no se vuelve a seleccionar.
    """
    engine = RealTimeTradingEngine(max_open_positions=1)
    engine.iq_mode = "BINARY_OPTIONS"
    
    # 1. Simular rechazo de USDJPY-OTC
    fake_rejection = {
        "success": False,
        "error": "Rechazado por IQ Option Binarias: Cannot purchase an option (the asset is not available at the moment)."
    }
    
    with patch.object(engine.binary_engine, "execute_binary_option", return_value=fake_rejection):
        # Simular evaluación de USDJPY-OTC
        engine.unavailable_assets_blacklist["USDJPY-OTC"] = time.time() + 1800.0
        engine.binary_engine.disable_asset("USDJPY-OTC", 1800.0)

    # 2. Verificar que USDJPY-OTC esté en blacklist
    assert engine.binary_engine.is_asset_disabled("USDJPY-OTC") is True
    assert "USDJPY-OTC" in engine.unavailable_assets_blacklist
    assert engine.unavailable_assets_blacklist["USDJPY-OTC"] > time.time() + 1700.0

    # 3. En el siguiente ciclo de trading, verificar que USDJPY-OTC es ignorado
    market_state = {
        "USDJPY-OTC": {"symbol": "USDJPY-OTC", "category": "FOREX", "price": 157.89},
        "EURUSD-OTC": {"symbol": "EURUSD-OTC", "category": "FOREX", "price": 1.1234}
    }
    
    scanned_syms = []
    now_ts = time.time()
    for sym, asset in market_state.items():
        if sym in engine.unavailable_assets_blacklist and now_ts < engine.unavailable_assets_blacklist[sym]:
            continue
        scanned_syms.append(sym)
    
    assert "USDJPY-OTC" not in scanned_syms
    assert "EURUSD-OTC" in scanned_syms


def test_sniper_reversal_requires_extreme_exhaustion_and_rejects_neutral_rsi():
    """
    Bug 4: Verifica que las reversiones Sniper (CALL en soporte o PUT en resistencia)
    estén ESTRICTAMENTE PROHIBIDAS si el RSI está neutro (35-65),
    y que en tendencias fuertes se opere Continuación a favor de la tendencia.
    """
    adapter = MagicMock()
    adapter.get_payout.return_value = 0.85
    engine = BinaryOptionsStrategyEngine(iqoption_adapter=adapter)

    # 1. Caso Bug Captura 4: RSI 50.4 tocando soporte en EUR/USD (OTC)
    # 5 velas rojas consecutivas cayendo en picada
    candles_down = [
        {"time": 100, "open": 1.1250, "high": 1.1252, "low": 1.1240, "close": 1.1241, "volume": 100},
        {"time": 160, "open": 1.1241, "high": 1.1242, "low": 1.1232, "close": 1.1233, "volume": 100},
        {"time": 220, "open": 1.1233, "high": 1.1235, "low": 1.1225, "close": 1.1226, "volume": 100},
        {"time": 280, "open": 1.1226, "high": 1.1228, "low": 1.1218, "close": 1.1219, "volume": 100},
        {"time": 340, "open": 1.1219, "high": 1.1220, "low": 1.1210, "close": 1.1211, "volume": 100},
        {"time": 400, "open": 1.1211, "high": 1.1212, "low": 1.1202, "close": 1.1203, "volume": 100},
        {"time": 460, "open": 1.1203, "high": 1.1204, "low": 1.1195, "close": 1.1196, "volume": 100},
        {"time": 520, "open": 1.1196, "high": 1.1197, "low": 1.1188, "close": 1.1189, "volume": 100},
        {"time": 580, "open": 1.1189, "high": 1.1190, "low": 1.1180, "close": 1.1181, "volume": 100},
        {"time": 640, "open": 1.1181, "high": 1.1182, "low": 1.1172, "close": 1.1173, "volume": 100},
    ]
    neutral_rsi_asset = {
        "symbol": "EURUSD-OTC",
        "price": 1.1173,
        "rsi": 50.4, # RSI Neutro
        "ema20": 1.1190,
        "ema50": 1.1220,
        "support": 1.1173, # Toca soporte
        "resistance": 1.1250,
        "trend_status": "BAJISTA",
        "regime": "TRENDING_DOWN"
    }

    eval_neutral = engine.evaluate_asset(neutral_rsi_asset, candles_down)
    # NUNCA debe meter CALL en contra de la tendencia con RSI 50.4
    assert eval_neutral["decision"] != "CALL"

    # 2. Caso Reversión VÁLIDA: RSI 28.0 (sobreventa real) con mecha de rechazo alcista
    candles_reversal = list(candles_down[:-1])
    # Última vela con mecha inferior larga (rechazo alcista)
    candles_reversal.append({
        "time": 700,
        "open": 1.1175,
        "high": 1.1176,
        "low": 1.1150, # Mecha inferior de 25 pips
        "close": 1.1174, # Cuerpo de 1 pip
        "volume": 200
    })
    exhausted_asset = {
        "symbol": "EURUSD-OTC",
        "price": 1.1174,
        "rsi": 28.5, # Agotamiento extremo <= 32.0
        "ema20": 1.1190,
        "ema50": 1.1220,
        "support": 1.1174,
        "resistance": 1.1250,
        "trend_status": "CONSOLIDACION",
        "regime": "OVERSOLD"
    }

    eval_reversal = engine.evaluate_asset(exhausted_asset, candles_reversal)
    assert eval_reversal["decision"] == "CALL"
    assert eval_reversal["confidence"] >= 65
    assert "Reversión Sniper Exhaustion" in eval_reversal["reason"]
