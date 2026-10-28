#!/usr/bin/env python3
"""Offline IQ Option configuration check; never opens a broker connection or order."""

from config.broker_config import load_broker_config, live_trading_armed, live_cfd_execution_verified


def diagnose() -> int:
    config = load_broker_config()
    credentials = config.get("iqoption", {})
    configured = bool(credentials.get("ssid") or (credentials.get("email") and credentials.get("password")))
    mode = str(config.get("iq_mode", "FOREX_CFD")).upper()
    environment = str(config.get("iqoption_environment", "PAPER")).upper()

    print(f"Credenciales configuradas: {'sí' if configured else 'no'}")
    print(f"Modalidad seleccionada: {mode}")
    print(f"Entorno guardado: {environment}")
    print(f"Armadura de real: {'sí' if live_trading_armed() else 'no'}")
    print(f"Sizing CFD marcado como verificado: {'sí' if live_cfd_execution_verified() else 'no'}")
    print("Diagnóstico local solamente: no se abrió conexión y no se enviaron órdenes.")

    if mode not in {"FOREX_CFD", "BINARY_OPTIONS"}:
        print("Advertencia: modalidad guardada desconocida; el motor debe rechazarla.")
        return 1
    if environment == "LIVE_REAL" and mode == "BINARY_OPTIONS":
        print("Binarias LIVE_REAL están bloqueadas hasta integrar liquidación oficial.")
    if environment == "LIVE_REAL" and not (live_trading_armed() and live_cfd_execution_verified()):
        print("CFD LIVE_REAL está bloqueado por las armaduras de proceso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(diagnose())
