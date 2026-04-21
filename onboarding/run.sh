#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
  venv/bin/pip install -q -r requirements.txt
fi

echo ""
echo "  ZivoPay Service Center  →  http://localhost:5001"
echo ""
venv/bin/python seed.py
PORT=5001 venv/bin/python main.py
