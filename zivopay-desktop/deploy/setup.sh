#!/usr/bin/env bash
# Deploy ZivoPay Desktop to a VPS
# Usage: bash setup.sh
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT=5090

echo "=== ZivoPay Desktop — Setup ==="

# 1. Install system deps
apt-get update -q
apt-get install -y python3-venv python3-pip nginx

# 2. Create virtualenv & install deps
cd "$APP_DIR"
python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt

# 3. Start app in background
pkill -f "app.py" 2>/dev/null || true
PORT=$PORT nohup venv/bin/python app.py >> app.log 2>&1 &
echo "App started on port $PORT (pid $!)"

# 4. Install nginx config
cp "$APP_DIR/deploy/nginx-mikrotik.conf" /etc/nginx/sites-available/mikrotik
ln -sf /etc/nginx/sites-available/mikrotik /etc/nginx/sites-enabled/mikrotik
nginx -t && nginx -s reload 2>/dev/null || nginx
echo "nginx configured → http://mikrotik.zivopay.online"

echo ""
echo "=== Done! ==="
echo "Open: http://mikrotik.zivopay.online"
echo "Login: admin / zivopay2026"
echo ""
echo "Go to Settings first to enter VPS SSH credentials"
echo "and WireGuard public key before onboarding clients."
