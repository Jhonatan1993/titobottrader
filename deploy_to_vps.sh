#!/bin/bash
set -e

VPS_IP="179.236.240.245"

echo "=========================================================="
echo "🚀 SUBIENDO Y DESPLEGANDO TITOBOTTRADER EN HOSTINGER VPS"
echo "Servidor IP Fija: $VPS_IP"
echo "=========================================================="

# 1. Asegurar que existe la carpeta en el VPS y sincronizar archivos
echo "📦 Transfiriendo código del bot al VPS..."
ssh root@$VPS_IP "mkdir -p /root/titobot"
rsync -avz --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.agents' ./ root@$VPS_IP:/root/titobot/

# 2. Ejecutar el script de aprovisionamiento en el VPS
echo "⚙️ Configurando dependencias y servicio 24/7 en el VPS..."
ssh root@$VPS_IP "bash /root/titobot/setup_vps.sh"

echo ""
echo "🎉 ¡Todo listo! Tu bot está operando en la nube."
echo "Ingresa en tu navegador a: http://$VPS_IP:5055"
