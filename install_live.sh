#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

sudo apt-get update
sudo apt-get install -y python3-venv

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

sudo cp pc-status-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pc-status-dashboard

echo "Dashboard live at: http://localhost:9080"
echo "Service status:"
systemctl status pc-status-dashboard --no-pager -n 20 || true
