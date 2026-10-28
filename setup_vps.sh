#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta este instalador como root o mediante sudo." >&2
  exit 1
fi

INSTALL_DIR="/opt/titobot"
SERVICE_FILE="/etc/systemd/system/titobot.service"

echo "Instalando TitoBotTrader con usuario de servicio sin privilegios..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-pip python3-venv ufw curl git rsync

if ! id -u titobot >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_DIR" --create-home --shell /usr/sbin/nologin titobot
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  if [ -e "$INSTALL_DIR" ] && [ "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 | wc -l)" -gt 0 ]; then
    echo "$INSTALL_DIR existe y no es un checkout Git; conserva los datos y migra la instalación manualmente." >&2
    exit 1
  fi
  git clone https://github.com/Jhonatan1993/titobottrader.git "$INSTALL_DIR"
fi

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

install -d -o titobot -g titobot -m 0750 "$INSTALL_DIR/data"
chown -R titobot:titobot "$INSTALL_DIR"
chmod 0700 "$INSTALL_DIR/data"
if [ -f "$INSTALL_DIR/.env" ]; then
  chmod 0600 "$INSTALL_DIR/.env"
fi

cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=TitoBotTrader dashboard and trading engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=titobot
Group=titobot
WorkingDirectory=/opt/titobot
EnvironmentFile=-/opt/titobot/.env
Environment=PYTHONUNBUFFERED=1
Environment=HOST=127.0.0.1
Environment=PORT=5050
Environment=SESSION_COOKIE_SECURE=true
Environment=LIVE_TRADING_ARMED=false
Environment=LIVE_CFD_EXECUTION_VERIFIED=false
ExecStart=/opt/titobot/venv/bin/gunicorn --workers 1 --bind 127.0.0.1:5050 --access-logfile - --error-logfile - main:app
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
ReadWritePaths=/opt/titobot/data

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$SERVICE_FILE"

echo "Restringiendo firewall a SSH y tráfico web detrás de Nginx..."
ufw delete allow 5050/tcp >/dev/null 2>&1 || true
ufw delete allow 5055/tcp >/dev/null 2>&1 || true
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP Nginx'
ufw allow 443/tcp comment 'HTTPS Nginx'
ufw --force enable

systemctl daemon-reload
systemctl enable titobot
systemctl restart titobot
sleep 2
systemctl --no-pager --full status titobot

echo "Servicio instalado en 127.0.0.1:5050. Configura Nginx/HTTPS antes de exponer el panel."
