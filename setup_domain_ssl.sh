#!/bin/bash
set -e

DOMAIN="titobottrader.tech"
EMAIL="admin@titobottrader.tech"

echo "=========================================================="
echo "🔒 CONFIGURANDO DOMINIO Y SSL (HTTPS) PARA $DOMAIN"
echo "=========================================================="

# 1. Instalar Nginx y Certbot
echo "📦 [1/4] Instalando Nginx y Certbot..."
apt-get update -y
apt-get install -y nginx certbot python3-certbot-nginx

# 2. Configurar Nginx Reverse Proxy hacia el bot (puerto 5050)
echo "⚙️ [2/4] Configurando proxy inverso en Nginx..."
cat << EOF > /etc/nginx/sites-available/$DOMAIN
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
EOF

# Habilitar sitio y deshabilitar default
ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# 3. Configurar Firewall para permitir tráfico Web HTTP y HTTPS
echo "🛡️ [3/4] Abriendo puertos 80 y 443 en el Firewall..."
ufw allow 'Nginx Full'
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 4. Obtener Certificado SSL gratuito de Let's Encrypt con auto-renovación
echo "📜 [4/4] Generando certificado SSL oficial (HTTPS)..."
certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos -m "$EMAIL" --redirect

echo ""
echo "=========================================================="
echo "🎉 ¡LISTO! TU PLATAFORMA YA ESTÁ EN VIVO CON HTTPS Y CANDADO:"
echo "👉 https://$DOMAIN"
echo "👉 https://www.$DOMAIN"
echo "=========================================================="
