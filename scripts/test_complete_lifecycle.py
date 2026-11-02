import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution.trading_engine import RealTimeTradingEngine

def test_full_battery():
    print("=" * 60)
    print("🚀 BATERÍA COMPLETA DE PRUEBAS EN TIEMPO REAL")
    print("=" * 60)

    # TEST 1: Apertura y Cierre por Take-Profit
    print("\n--- TEST 1: APERTURA Y TAKE-PROFIT ---")
    engine = RealTimeTradingEngine(initial_balance=10000.0, execution_environment="PAPER")
    assert len(engine.open_positions) == 0
    engine.step()
    assert len(engine.open_positions) == 1, "Debe abrir posición"
    sym = list(engine.open_positions.keys())[0]
    pos = engine.open_positions[sym]
    tp_p = pos["take_profit"]
    print(f"  Posición abierta: {sym} (TP: {tp_p})")
    
    # Simular TP
    engine.feed.candles[sym][-1]["close"] = tp_p + 0.05
    engine.feed.assets[sym]["price"] = tp_p + 0.05
    engine.step()
    assert len(engine.open_positions) == 0, "Debe cerrarse por TP"
    print("  ✅ TEST 1 SUPERADO: Posición cerrada por Take Profit.")

    # TEST 2: Apertura y Cierre por Stop-Loss
    print("\n--- TEST 2: APERTURA Y STOP-LOSS ---")
    # Forzar reseteo de cooldown en sym para permitir nueva apertura
    engine.last_exit_times.clear()
    engine._last_iqoption_trade_time = 0.0
    engine.step()
    assert len(engine.open_positions) == 1, "Debe abrir una nueva posición"
    sym2 = list(engine.open_positions.keys())[0]
    pos2 = engine.open_positions[sym2]
    sl_p = pos2["stop_loss"]
    print(f"  Posición abierta: {sym2} (SL: {sl_p})")
    
    # Simular SL catastrófico
    engine.feed.candles[sym2][-1]["close"] = sl_p - 0.05
    engine.feed.assets[sym2]["price"] = sl_p - 0.05
    engine.step()
    assert len(engine.open_positions) == 0, "Debe cerrarse por SL"
    print("  ✅ TEST 2 SUPERADO: Posición cerrada por Stop Loss.")

    # TEST 3: Break-Even y Trailing Stop dinámico
    print("\n--- TEST 3: BREAK-EVEN Y TRAILING STOP ---")
    engine.last_exit_times.clear()
    engine._last_iqoption_trade_time = 0.0
    engine.step()
    assert len(engine.open_positions) == 1
    sym3 = list(engine.open_positions.keys())[0]
    pos3 = engine.open_positions[sym3]
    entry_3 = pos3["entry_price"]
    initial_sl_3 = pos3["stop_loss"]
    print(f"  Posición abierta: {sym3} | Entrada: {entry_3} | SL Inicial: {initial_sl_3}")
    
    # Simular paso del tiempo (>10s) y movimiento favorable
    pos3["entry_timestamp"] = time.time() - 15.0
    engine.feed.candles[sym3][-1]["close"] = entry_3 + (abs(entry_3 - initial_sl_3) * 1.2)
    engine.feed.assets[sym3]["price"] = engine.feed.candles[sym3][-1]["close"]
    engine.step()
    
    assert pos3.get("is_break_even") is True, "El Break-Even debió activarse"
    assert pos3["stop_loss"] >= entry_3, "El Stop-Loss debió subirse al precio de entrada"
    print(f"  ✅ TEST 3 SUPERADO: Break-Even activado. Nuevo SL protegido: {pos3['stop_loss']} >= Entrada ({entry_3})")

    print("\n" + "=" * 60)
    print("🏆 TODAS LAS PRUEBAS DE OPERACIÓN EN VIVO FUNCIONAN AL 100%")
    print("=" * 60)

if __name__ == "__main__":
    test_full_battery()
