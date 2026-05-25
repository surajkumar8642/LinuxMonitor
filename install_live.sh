#!/usr/bin/env bash
set -euo pipefail

cd /home/comp5/pc-status-dashboard
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
