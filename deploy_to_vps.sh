#!/bin/bash
set -e

VPS_IP="179.198.222.207"

echo "=========================================================="
echo "🚀 SUBIENDO Y DESPLEGANDO TITOBOTTRADER EN HOSTINGER VPS"
echo "Servidor IP Fija: $VPS_IP"
echo "=========================================================="

# 1. Asegurar que existe la carpeta en el VPS y sincronizar archivos
echo "📦 Transfiriendo código del bot al VPS..."
ssh root@$VPS_IP "mkdir -p /root/titobot"
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.agents' ./ root@$VPS_IP:/root/titobot/

# 2. Reiniciar servicio en el VPS
echo "🔄 Reiniciando servicio titobot en el VPS..."
ssh root@$VPS_IP "systemctl restart titobot && sleep 2 && systemctl status titobot --no-pager"

echo ""
echo "🎉 ¡Todo listo! Tu bot está operando en la nube con las correcciones activas."
echo "Ingresa en tu navegador a: https://titobottrader.tech"
