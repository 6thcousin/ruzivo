#!/bin/bash
# setup.sh — deploy ZivoPay Onboarding on the VPS
# Run as root: bash setup.sh
set -e

APP_DIR="/opt/zivopay-onboarding"
DOMAIN="onboarding.zivopay.online"
SERVICE="zivopay-onboarding"

echo ""
echo "======================================================"
echo "  ZivoPay Onboarding — VPS Setup"
echo "  Domain: $DOMAIN"
echo "======================================================"
echo ""

# ── 1. Install system deps ────────────────────────────────────────────────────
echo "[1/7] Installing system packages..."
apt-get update -q
apt-get install -y -q python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# ── 2. Copy app files ─────────────────────────────────────────────────────────
echo "[2/7] Deploying app to $APP_DIR..."
mkdir -p "$APP_DIR"
cp -r ./* "$APP_DIR/"
mkdir -p "$APP_DIR/data"
cd "$APP_DIR"

# ── 3. Python venv + deps ─────────────────────────────────────────────────────
echo "[3/7] Creating Python virtualenv..."
python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt

# ── 4. Systemd service ────────────────────────────────────────────────────────
echo "[4/7] Installing systemd service..."
cp deploy/zivopay-onboarding.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" && echo "  [✓] Service running" || echo "  [!] Service failed — check: journalctl -u $SERVICE"

# ── 5. Nginx ──────────────────────────────────────────────────────────────────
echo "[5/7] Configuring Nginx..."
cp deploy/nginx.conf /etc/nginx/sites-available/zivopay-onboarding

# Temporarily use HTTP-only config for certbot
cat > /etc/nginx/sites-available/zivopay-onboarding-temp << 'NGINX'
server {
    listen 80;
    server_name onboarding.zivopay.online;
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/zivopay-onboarding-temp /etc/nginx/sites-enabled/zivopay-onboarding
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
echo "  [✓] Nginx configured (HTTP only, for cert issuance)"

# ── 6. SSL certificate ────────────────────────────────────────────────────────
echo "[6/7] Obtaining SSL certificate for $DOMAIN..."
echo "      (Make sure DNS A record points $DOMAIN → $(curl -s ifconfig.me))"
echo ""
read -p "Press ENTER when DNS is ready, or Ctrl+C to skip SSL for now... "

certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
    --email admin@zivopay.online --redirect 2>&1 | tail -5

# Now install the full nginx config with SSL
ln -sf /etc/nginx/sites-available/zivopay-onboarding /etc/nginx/sites-enabled/zivopay-onboarding
nginx -t && systemctl reload nginx
echo "  [✓] SSL enabled"

# ── 7. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "[7/7] Done!"
echo ""
echo "  App URL  : https://$DOMAIN"
echo "  Login    : admin / zivopay2026"
echo "  Logs     : journalctl -u $SERVICE -f"
echo "  Restart  : systemctl restart $SERVICE"
echo ""
echo "  IMPORTANT: Change the admin password in:"
echo "  /etc/systemd/system/$SERVICE.service  (ADMIN_PASS=)"
echo "  Then: systemctl daemon-reload && systemctl restart $SERVICE"
echo ""
