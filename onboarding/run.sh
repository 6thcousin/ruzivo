#!/bin/bash
# run.sh — start ZivoPay Onboarding
cd "$(dirname "$0")"

# Install deps if venv missing
if [ ! -d "venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
  venv/bin/pip install -q -r requirements.txt
fi

echo ""
echo "  ZivoPay Onboarding  →  http://localhost:5001"
echo ""
PORT=5001 venv/bin/python app.py
