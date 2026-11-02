import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution.trading_engine import RealTimeTradingEngine

def run_diagnostics():
    print("=" * 60)
    print("🔍 INICIANDO DIAGNÓSTICO EN TIEMPO REAL DEL MOTOR DE TRADING")
    print("=" * 60)

    engine = RealTimeTradingEngine(initial_balance=10000.0, execution_environment="PAPER")
    print(f"1. Engine is_running: {engine.is_running}")
    print(f"2. Active broker: {engine.active_broker}")
    print(f"3. Operating mode: {engine.operating_mode}")
    print(f"4. IQ mode: {getattr(engine, 'iq_mode', 'N/A')}")
    print(f"5. Execution environment: {engine.execution_environment}")
    print(f"6. Target reached: {engine.target_reached}")
    print(f"7. Loss limit reached: {getattr(engine, 'loss_limit_reached', False)}")
    print(f"8. Max open positions allowed: {engine.max_open_positions}")
    print(f"9. Risk policy halted: {engine.iqoption_risk_policy.halted} ({engine.iqoption_risk_policy.halted_reason})")
    
    wallet = engine.broker_wallets.get("IQOPTION", {})
    print(f"10. IQ Wallet: cash=${wallet.get('cash')}, is_running={wallet.get('is_running')}, env={wallet.get('environment')}")
    
    print("\n" + "=" * 60)
    print("🔬 SIMULANDO 5 CICLOS DE MERCADO CON STEP()...")
    print("=" * 60)

    for i in range(1, 6):
        print(f"\n--- CICLO #{i} ---")
        engine.step()
        print(f"Posiciones abiertas actuales: {len(engine.open_positions)}")
        for sym, pos in engine.open_positions.items():
            print(f"  -> Activa: {sym} | Tipo: {pos.get('trade_type')} | Lado: {pos.get('side')} | SL: {pos.get('stop_loss')} | TP: {pos.get('take_profit')} | Status: {pos.get('execution_status')}")
        
        # Mostrar los últimos pensamientos del agente
        recent_thoughts = getattr(engine.agent, 'thoughts', [])[-5:]
        print("  Últimos pensamientos del agente:")
        for t in recent_thoughts:
            print(f"    [{t.get('time')}] {t.get('thought')}")
        time.sleep(1.0)

if __name__ == "__main__":
    run_diagnostics()
