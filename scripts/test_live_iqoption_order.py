#!/usr/bin/env python3
"""
Test de Ejecución Real en IQ Option (Demo / Practice).
Conecta directamente a los servidores WebSocket de IQ Option con las credenciales
configuradas en el bot, consulta balances reales/demo y, si se solicita, envía
una orden real de prueba a la cuenta de práctica de IQ Option.

Uso:
    python3 scripts/test_live_iqoption_order.py
    python3 scripts/test_live_iqoption_order.py --symbol EURUSD --amount 1.0 --side buy
"""

import sys
import time
import argparse
from config.broker_config import load_broker_config
from execution.iqoption_adapter import IQOptionAdapter, ACTIVE_ASSET_IDS


def main():
    parser = argparse.ArgumentParser(description="Test de conexión y ejecución real con IQ Option")
    parser.add_argument("--symbol", default="EURUSD", help="Par a operar (default: EURUSD)")
    parser.add_argument("--side", default="buy", choices=["buy", "sell"], help="Dirección (buy/sell)")
    parser.add_argument("--amount", type=float, default=None, help="Importe (default: mínimo por divisa)")
    parser.add_argument("--env", default="PAPER", choices=["PAPER", "LIVE_REAL"], help="Entorno de prueba (PAPER o LIVE_REAL)")
    parser.add_argument("--confirm-real", action="store_true", help="Confirmación explícita requerida para operar en LIVE_REAL")
    parser.add_argument("--skip-order", action="store_true", help="Solo verificar conexión y balances sin enviar orden")
    parser.add_argument("--close-after", type=int, default=10, help="Segundos antes de cerrar la orden de prueba (default: 10s)")
    args = parser.parse_args()

    if args.env == "LIVE_REAL" and not args.skip_order and not args.confirm_real:
        print("\n🛑 SEGURIDAD: Para enviar una orden en cuenta REAL (LIVE_REAL) debes incluir el parámetro --confirm-real")
        return 1

    print("=" * 70)
    print("🛰️  TEST DE CONEXIÓN Y EJECUCIÓN DIRECTA CON IQ OPTION")
    print("=" * 70)

    config = load_broker_config()
    creds = config.get("iqoption", {})
    ssid = creds.get("ssid", "")
    email = creds.get("email", "")
    pwd = creds.get("password", "")

    print(f"[*] Credenciales detectadas:")
    print(f"    - Email: {email if email else '(no configurado)'}")
    print(f"    - SSID: {ssid[:12] + '...' if ssid else '(no configurado)'}")
    print(f"    - Modalidad: {config.get('iq_mode', 'FOREX_CFD')}")
    print(f"    - Entorno bot: {config.get('iqoption_environment', 'PAPER')}")

    if not ssid and not (email and pwd):
        print("\n❌ ERROR: No hay credenciales configuradas en data/broker_config.json")
        return 1

    print("\n[1/4] Iniciando sesión en WebSocket oficial de IQ Option...")
    adapter = IQOptionAdapter(email=email, password=pwd, ssid=ssid, environment=args.env)
    auth_res = adapter.connect()

    print(f"    - Conectado: {auth_res.get('connected')}")
    print(f"    - Nombre usuario: {auth_res.get('name')}")
    print(f"    - Divisa cuenta: {adapter.currency}")
    print(f"    - Saldo Cuenta DEMO / Práctica: ${adapter.practice_amount:,.2f} {adapter.currency}")
    print(f"    - Saldo Cuenta REAL: ${adapter.real_amount:,.2f} {adapter.currency}")
    print(f"    - ID Balance Práctica: {adapter.practice_balance_id}")
    print(f"    - ID Balance Real: {adapter.real_balance_id}")

    if not auth_res.get("connected"):
        print(f"\n❌ Error de autenticación: {auth_res.get('error')}")
        print("💡 Sugerencia: Copia el token 'ssid' actualizado desde las cookies de tu navegador en iqoption.com")
        return 1

    print("\n✅ Conexión establecida exitosamente con el broker IQ Option.")

    if args.skip_order:
        print("\n[INFO] Flag --skip-order activada: omitiendo envío de orden.")
        return 0

    sym = args.symbol.upper()
    active_id = adapter.get_active_id(sym)
    print(f"\n[2/4] Verificando instrumento {sym}:")
    print(f"    - Active ID: {active_id}")
    print(f"    - Instrument ID WebSocket: mf.{active_id}")

    min_amount = 2000.0 if adapter.currency == "COP" else 1.0
    order_amount = args.amount if args.amount is not None else min_amount

    print(f"\n[3/4] Enviando orden de prueba en CUENTA PRÁCTICA (DEMO) de IQ Option:")
    print(f"    - Símbolo: {sym}")
    print(f"    - Dirección: {args.side.upper()}")
    print(f"    - Importe: ${order_amount:,.2f} {adapter.currency}")
    print(f"    - Apalancamiento: x25")
    print(f"    - Balance destino: Práctica ({adapter.practice_balance_id})")

    start_t = time.time()
    order_res = adapter.submit_order(
        symbol=sym,
        side=args.side,
        amount=order_amount,
        leverage=25,
        stop_loss_pct=1.0,
        take_profit_pct=2.0
    )
    elapsed = time.time() - start_t

    print(f"\n[4/4] Respuesta oficial del Broker IQ Option (en {elapsed:.2f}s):")
    for k, v in order_res.items():
        print(f"    - {k}: {v}")

    if order_res.get("success") and str(order_res.get("status")) == "FILLED":
        order_id = order_res.get("order_id")
        print(f"\n🎉 ¡ORDEN EJECUTADA EXITOSAMENTE EN IQ OPTION!")
        print(f"   ID Oficial de la Orden: {order_id}")
        print(f"   Esta orden ya está visible en tu pantalla de IQ Option en la cuenta de Práctica.")

        if args.close_after > 0:
            print(f"\n⏳ Manteniendo orden abierta {args.close_after}s antes de cerrarla automáticamente...")
            time.sleep(args.close_after)
            print(f"[*] Cerrando posición {order_id} en IQ Option...")
            close_res = adapter.close_position(str(order_id))
            print(f"    - Resultado del cierre: {close_res}")
            if close_res.get("success"):
                print("✅ Posición cerrada en IQ Option.")
            else:
                print(f"⚠️ Nota de cierre: {close_res.get('error')}")
        return 0
    else:
        print(f"\n❌ La orden no pudo ser ejecutada por el broker:")
        print(f"   Detalle: {order_res.get('error')}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
