#!/bin/bash
# install_vps.sh — full one-shot installer for ZivoPay Onboarding on VPS
# Run:  bash install_vps.sh
set -e

APP_DIR="/opt/zivopay-onboarding"
SERVICE="zivopay-onboarding"
REPO="https://github.com/6thcousin/ruzivo"   # update if private
BRANCH="claude/register-wg-client-vps-RdiYm"

echo ""
echo "======================================================"
echo "  ZivoPay Service Center — VPS Installer"
echo "======================================================"
echo ""

# ── System deps ───────────────────────────────────────────────────────────────
echo "[1] Installing system packages..."
apt-get update -q
apt-get install -y -q python3 python3-pip python3-venv nginx git curl

# ── Clone / update repo ───────────────────────────────────────────────────────
echo "[2] Fetching app code..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
    echo "  [✓] Repo updated"
else
    git clone --branch "$BRANCH" --depth 1 "$REPO" "$APP_DIR"
    echo "  [✓] Repo cloned to $APP_DIR"
fi

cd "$APP_DIR/onboarding"

# ── Python venv ───────────────────────────────────────────────────────────────
echo "[3] Setting up Python virtualenv..."
python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt
echo "  [✓] Packages installed"

# ── Data dir ─────────────────────────────────────────────────────────────────
mkdir -p data

# ── Seed database ─────────────────────────────────────────────────────────────
echo "[4] Seeding router database..."
venv/bin/python seed_routers.py

# ── Systemd service ───────────────────────────────────────────────────────────
echo "[5] Installing systemd service..."
cat > /etc/systemd/system/zivopay-onboarding.service << 'SVCEOF'
[Unit]
Description=ZivoPay Onboarding Service Center
After=network.target

[Service]
User=root
WorkingDirectory=/opt/zivopay-onboarding/onboarding
Environment="SECRET_KEY=zivopay-secret-change-me"
Environment="ADMIN_USER=admin"
Environment="ADMIN_PASS=zivopay2026"
Environment="WG_INTERFACE=wg0"
Environment="VPS_WG_IP=10.0.0.1"
Environment="WG_SUBNET=10.0.0.0/24"
ExecStart=/opt/zivopay-onboarding/onboarding/venv/bin/gunicorn \
    --workers 2 --bind 127.0.0.1:5001 --timeout 60 \
    --access-logfile /var/log/zivopay-onboarding.log \
    --error-logfile /var/log/zivopay-onboarding.log \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
    echo "  [✓] Service running on port 5001"
else
    echo "  [!] Service failed. Check: journalctl -u $SERVICE --no-pager -n 30"
    journalctl -u "$SERVICE" --no-pager -n 20
    exit 1
fi

# ── Nginx ─────────────────────────────────────────────────────────────────────
echo "[6] Configuring Nginx..."
cat > /etc/nginx/sites-available/zivopay-onboarding << 'NGINXEOF'
server {
    listen 80;
    server_name onboarding.zivopay.online _;

    location / {
        proxy_pass         http://127.0.0.1:5001;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/zivopay-onboarding /etc/nginx/sites-enabled/zivopay-onboarding
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
echo "  [✓] Nginx configured"

# ── Test ─────────────────────────────────────────────────────────────────────
echo "[7] Testing..."
sleep 1
CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/)
if [ "$CODE" = "200" ] || [ "$CODE" = "302" ]; then
    echo "  [✓] App responding (HTTP $CODE)"
else
    echo "  [!] App returned HTTP $CODE"
fi

VPS_IP=$(curl -s ifconfig.me 2>/dev/null || echo "unknown")

echo ""
echo "======================================================"
echo "  DONE!"
echo ""
echo "  Local:   http://localhost:5001"
echo "  Public:  http://$VPS_IP  (port 80)"
echo "  Domain:  http://onboarding.zivopay.online"
echo "           (after DNS A record: onboarding → $VPS_IP)"
echo ""
echo "  Login:   admin / zivopay2026"
echo ""
echo "  Change password:"
echo "  nano /etc/systemd/system/zivopay-onboarding.service"
echo "  systemctl daemon-reload && systemctl restart $SERVICE"
echo ""
echo "  For SSL (after DNS is set):"
echo "  apt install certbot python3-certbot-nginx -y"
echo "  certbot --nginx -d onboarding.zivopay.online"
echo "======================================================"
echo ""
