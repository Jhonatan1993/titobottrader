#!/usr/bin/env python3
"""
Script de Certificación y Prueba Real en Producción de Opciones Binarias con IQ Option.
Ejecuta 1 sola orden controlada por la cantidad mínima legal (COP 2,000 o USD 1.0)
y valida la respuesta oficial devuelta por el servidor WebSocket de IQ Option.
"""

import sys
import os
import time
import json

# Agregar ruta base del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.broker_config import load_broker_config
from execution.iqoption_adapter import IQOptionAdapter, ACTIVE_ASSET_IDS

def main():
    print("=" * 70)
    print("🔬 PRUEBA CONTROLADA DE OPCIONES BINARIAS EN IQ OPTION (1 ORDEN REAL)")
    print("=" * 70)

    cfg = load_broker_config()
    iq_cfg = cfg.get("iqoption", {})
    email = iq_cfg.get("email", "")
    ssid = iq_cfg.get("ssid", "")
    env = cfg.get("iqoption_environment", "LIVE_REAL")

    print(f"📧 Usuario configurado: {email or 'Sesión por SSID'}")
    print(f"🌐 Entorno: {env}")

    adapter = IQOptionAdapter(
        email=email,
        password=iq_cfg.get("password", ""),
        ssid=ssid,
        environment="LIVE_REAL"
    )

    print("\n⏳ Conectando con IQ Option y validando saldo real...")
    conn = adapter.connect()
    if not conn.get("connected"):
        print(f"❌ Error de conexión: {conn.get('error', 'No se pudo autenticar')}")
        sys.exit(1)

    currency = adapter.currency or "COP"
    balance = adapter.real_amount if adapter.real_amount > 0 else adapter.balance
    print(f"✅ Conexión Exitosa!")
    print(f"💰 Saldo Real Disponible: {balance:,.2f} {currency}")
    print(f"🆔 Balance ID: {adapter.real_balance_id}")

    min_amount = 2000.0 if currency == "COP" else 1.0
    if balance < min_amount:
        print(f"❌ Saldo insuficiente en la cuenta real. Se requiere al menos {min_amount:,.2f} {currency}.")
        sys.exit(1)

    # Par a operar: seleccionar uno con alta liquidez y payout
    target_symbol = sys.argv[1] if len(sys.argv) > 1 else "EURJPY"
    direction = sys.argv[2].upper() if len(sys.argv) > 2 else "CALL"
    amount = float(sys.argv[3]) if len(sys.argv) > 3 else min_amount

    print(f"\n🎯 Lanzando Orden de Prueba Controlada:")
    print(f"   • Activo: {target_symbol}")
    print(f"   • Dirección: {direction} (Sube)")
    print(f"   • Monto Inversión: {amount:,.2f} {currency}")
    print(f"   • Duración: 1 minuto (Turbo 60s)")
    print(f"   • Política de Riesgo: 1 SOLA OPERACIÓN SIMULTÁNEA (0/1)")

    print("\n📡 Transmitiendo orden al servidor WebSocket de IQ Option...")
    order_result = adapter.submit_binary_option(
        symbol=target_symbol,
        direction=direction,
        amount=amount,
        duration_minutes=1
    )

    print("\n" + "=" * 70)
    if order_result.get("success"):
        oid = order_result.get("order_id")
        exp_ts = order_result.get("expiration_timestamp")
        payout = order_result.get("payout", 0.85)
        print("🏆 ¡OPERACIÓN REGISTRADA EXITOSAMENTE EN IQ OPTION!")
        print(f"   • ID Oficial de la Orden: {oid}")
        print(f"   • Estado: {order_result.get('status', 'OPENED')}")
        print(f"   • Expiración Timestamp: {exp_ts}")
        print(f"   • Payout Estimado: {int(payout * 100)}%")
        print(f"\n👉 Ya puedes verla en tu pantalla de IQ Option:")
        print(f"   iqoption.com/pwa/trades?tab=options (Pestaña 'Activas')")
    else:
        print("⚠️ La orden fue rechazada por el broker:")
        print(f"   Error: {order_result.get('error')}")
    print("=" * 70)

if __name__ == "__main__":
    main()
