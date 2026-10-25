#!/bin/bash
# ==============================================================================
# TITOBOTTRADER - OPTIMIZACIÓN SEMANAL CUANTITATIVA (CRON DOMINGOS)
# Ejecuta Grid Search para calibrar parámetros de mercado antes de apertura semanal
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="$SCRIPT_DIR/venv/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "=========================================================="
echo "🎯 Iniciando Optimización Semanal de Parámetros [$(date)]"
echo "=========================================================="

"$PYTHON_BIN" optimizer.py --candles 2500

echo "✅ Optimización finalizada exitosamente."
echo "Los nuevos parámetros han sido recargados automáticamente en caliente por el bot."
