#!/usr/bin/env python3
import json
import shutil
import socket
import subprocess
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# Put your custom service names here.
CUSTOM_FETCHERS = [
    "fetcher-a.service",
    "fetcher-b.service",
]

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>PC Status Dashboard</title>
  <style>
    :root {
      --bg: #0b1320;
      --card: #132038;
      --text: #e8eef9;
      --muted: #9ab0d3;
      --ok: #1ec98f;
      --warn: #ffbe55;
      --bad: #ff5c7a;
      --line: #284267;
    }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background: radial-gradient(circle at top right, #1d3154 0, #0b1320 55%); color: var(--text); }
    .wrap { max-width: 1100px; margin: 28px auto; padding: 0 16px; }
    h1 { margin: 0 0 4px; font-size: 28px; }
    p.sub { margin: 0 0 20px; color: var(--muted); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(240px,1fr)); gap: 14px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }
    .title { font-size: 14px; color: var(--muted); margin-bottom: 8px; }
    .value { font-size: 18px; font-weight: 700; }
    .ok { color: var(--ok); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    table { width: 100%; border-collapse: collapse; }
    td, th { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; font-size: 14px; }
    .btn { margin-top: 16px; background: #22406b; color: #fff; border: 0; border-radius: 8px; padding: 8px 12px; cursor: pointer; }
    .small { font-size: 12px; color: var(--muted); }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>PC Status Dashboard</h1>
    <p class="sub">Host: {{ host }} | Last update: <span id="updated"></span></p>

    <div class="grid" id="top"></div>

    <div class="card" style="margin-top:14px;">
      <div class="title">Custom Fetchers</div>
      <table>
        <thead><tr><th>Service</th><th>Status</th><th>Enabled</th></tr></thead>
        <tbody id="fetchers"></tbody>
      </table>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="title">Network Interfaces</div>
      <table>
        <thead><tr><th>Interface</th><th>State</th><th>IP</th></tr></thead>
        <tbody id="ifaces"></tbody>
      </table>
    </div>

    <button class="btn" onclick="load()">Refresh</button>
    <div class="small">API: /api/status</div>
  </div>

<script>
function cls(v){ if(v==='active' || v==='running' || v===true) return 'ok'; if(v==='inactive' || v==='unknown') return 'warn'; return 'bad'; }
function text(v){ return (v===true)?'yes':(v===false)?'no':String(v); }
async function load(){
  const r = await fetch('/api/status');
  const d = await r.json();
  document.getElementById('updated').textContent = d.timestamp;

  const top = [
    ['SSH', d.services.ssh.active],
    ['SMB', d.services.smb.active],
    ['Firewall (ufw)', d.services.ufw.status],
    ['Internet', d.network.internet],
  ];
  document.getElementById('top').innerHTML = top.map(([k,v]) => `<div class="card"><div class="title">${k}</div><div class="value ${cls(v)}">${text(v)}</div></div>`).join('');

  document.getElementById('fetchers').innerHTML = d.custom_fetchers.map(s =>
    `<tr><td>${s.name}</td><td class="${cls(s.active)}">${s.active}</td><td>${s.enabled}</td></tr>`).join('');

  document.getElementById('ifaces').innerHTML = d.network.interfaces.map(i =>
    `<tr><td>${i.name}</td><td class="${cls(i.state)}">${i.state}</td><td>${i.ip || '-'}</td></tr>`).join('');
}
load();
</script>
</body>
</html>
"""


def run(cmd):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return p.stdout.strip()


def service_status(name):
    active = run(f"systemctl is-active {name}") or "unknown"
    enabled = run(f"systemctl is-enabled {name}") or "unknown"
    return {"name": name, "active": active, "enabled": enabled}


def ufw_status():
    if not shutil.which("ufw"):
        return "not-installed"
    out = run("ufw status | head -n1")
    if "active" in out.lower():
        return "active"
    if "inactive" in out.lower():
        return "inactive"
    return "unknown"


def internet_ok():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        return True
    except OSError:
        return False


def interfaces():
    out = run("ip -o -4 addr show")
    state_map = {}
    link_out = run("ip -o link show")
    for line in link_out.splitlines():
        parts = line.split(": ", 2)
        if len(parts) >= 3:
            name = parts[1].split("@")[0]
            state_map[name] = "UP" if " state UP " in line else "DOWN"
    rows = []
    seen = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            name = parts[1]
            ip = parts[3]
            seen.add(name)
            rows.append({"name": name, "state": state_map.get(name, "unknown"), "ip": ip})
    for name, st in state_map.items():
        if name not in seen and not name.startswith("lo"):
            rows.append({"name": name, "state": st, "ip": ""})
    return sorted(rows, key=lambda x: x["name"])


@app.route("/")
def index():
    return render_template_string(TEMPLATE, host=socket.gethostname())


@app.route("/api/status")
def api_status():
    ssh = service_status("ssh.service")
    smb = service_status("smbd.service")
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "host": socket.gethostname(),
        "services": {
            "ssh": ssh,
            "smb": smb,
            "ufw": {"status": ufw_status()},
        },
        "custom_fetchers": [service_status(s) for s in CUSTOM_FETCHERS],
        "network": {
            "internet": internet_ok(),
            "interfaces": interfaces(),
        },
    }
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9080)
