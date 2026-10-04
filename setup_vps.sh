#!/bin/bash
set -e

echo "=========================================================="
echo "🚀 INICIANDO DESPLIEGUE DE TITOBOTTRADER EN HOSTINGER VPS"
echo "=========================================================="

# 1. Actualizar repositorios e instalar paquetes base
echo "📦 [1/6] Actualizando sistema y dependencias de Linux..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-pip python3-venv ufw curl git rsync

# 2. Configurar Firewall seguro
echo "🛡️ [2/6] Configurando Firewall UFW..."
ufw allow 22/tcp comment 'SSH'
ufw allow 5050/tcp comment 'TitoBotTrader Dashboard 5050'
ufw allow 5055/tcp comment 'TitoBotTrader Dashboard 5055'
ufw --force enable


# 3. Descargar o actualizar desde GitHub
echo "📥 [3/7] Obteniendo el código desde GitHub..."
INSTALL_DIR="/root/titobot"
if [ ! -d "$INSTALL_DIR/.git" ]; then
    rm -rf "$INSTALL_DIR"
    git clone https://github.com/Jhonatan1993/titobottrader.git "$INSTALL_DIR"
else
    cd "$INSTALL_DIR"
    git pull origin main
fi

# 4. Crear entorno virtual de Python
echo "🐍 [4/7] Creando entorno virtual aislado de Python..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate

# 4. Instalar librerías
echo "📚 [4/6] Instalando requerimientos cuantitativos..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Crear Servicio de Sistema (systemd) para operación 24/7 permanente
echo "⚙️ [5/6] Configurando servicio 24/7 (systemd)..."
cat << 'EOF' > /etc/systemd/system/titobot.service
[Unit]
Description=TitoBotTrader - Motor Cuantitativo 24/7
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/titobot
ExecStart=/root/titobot/venv/bin/python3 /root/titobot/main.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 6. Recargar y activar servicio
echo "🚀 [6/6] Activando servicio en segundo plano..."
systemctl daemon-reload
systemctl enable titobot
systemctl restart titobot

sleep 3
systemctl status titobot --no-pager

echo ""
echo "=========================================================="
echo "✅ ¡TITOBOTTRADER DESPLEGADO Y OPERANDO 24/7 CON ÉXITO!"
echo "Accede a tu panel en:"
echo "👉 http://179.236.240.245:5055"
echo "=========================================================="
