# PC Status Dashboard (Ubuntu)

## Install

```bash
cd /home/comp5/pc-status-dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python status_dashboard.py
```

Open: http://localhost:9080

## Add your custom fetchers

Edit `CUSTOM_FETCHERS` in `status_dashboard.py`, example:

```python
CUSTOM_FETCHERS = [
  "my-fetcher.service",
  "sync-fetcher.service",
  "worker-fetcher.service",
]
```

Each fetcher should be a `systemd` service for accurate active/enabled status.

## Run as live service (auto-start)

```bash
cd /home/comp5/pc-status-dashboard
./install_live.sh
```

Check status:

```bash
systemctl status pc-status-dashboard
journalctl -u pc-status-dashboard -f
```
