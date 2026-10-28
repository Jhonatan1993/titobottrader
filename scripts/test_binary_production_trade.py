#!/usr/bin/env python3
"""Local binary PAPER preview. This script does not connect to IQ Option."""

import sys

from execution.iqoption_adapter import IQOptionAdapter


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    direction = sys.argv[2].upper() if len(sys.argv) > 2 else "CALL"
    amount = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    adapter = IQOptionAdapter(environment="PAPER")
    result = adapter.submit_binary_option(symbol, direction, amount, duration_minutes=1)
    print(f"Resultado local PAPER: {result}")
    print("No se abrió conexión al broker ni se envió una orden.")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
