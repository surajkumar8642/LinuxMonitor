#!/usr/bin/env python3
import os
import shutil
import socket
import subprocess
import ipaddress
from datetime import datetime

from flask import Flask, jsonify, render_template_string
from flask import request

app = Flask(__name__)
os.environ["PATH"] = os.environ.get("PATH", "") + ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

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
    .clickable { cursor: pointer; transition: border-color .15s ease; }
    .clickable:hover { border-color: #4f79b8; }
    .title { font-size: 14px; color: var(--muted); margin-bottom: 8px; }
    .value { font-size: 18px; font-weight: 700; }
    .ok { color: var(--ok); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    table { width: 100%; border-collapse: collapse; }
    td, th { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; font-size: 14px; }
    tr.clickable:hover { background: rgba(79, 121, 184, 0.16); }
    .btn { margin-top: 16px; background: #22406b; color: #fff; border: 0; border-radius: 8px; padding: 8px 12px; cursor: pointer; }
    .small { font-size: 12px; color: var(--muted); }
    .chip { display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid var(--line); font-size:12px; margin-right:6px; }
    .ico { display:inline-block; width:18px; text-align:center; margin-right:6px; color:#7fb0ff; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>PC Status Dashboard</h1>
    <p class="sub">Host: {{ host }} | Last update: <span id="updated"></span></p>

    <div class="grid" id="top"></div>

    <div class="card" style="margin-top:14px;">
      <div class="title"><span class="ico">#</span>User Insights</div>
      <table>
        <thead><tr><th>User</th><th>Type</th><th>Source</th><th>Status</th></tr></thead>
        <tbody id="users"></tbody>
      </table>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="title"><span class="ico">@</span>Access Matrix (Who Access What)</div>
      <table>
        <thead><tr><th>User/Process</th><th>Resource</th><th>Path/Target</th><th>Access</th></tr></thead>
        <tbody id="access"></tbody>
      </table>
    </div>

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

    <div class="card" style="margin-top:14px;">
      <div class="title"><span class="ico">*</span>Firewall Flow (Local/Internal vs External)</div>
      <div style="margin-bottom:8px;">
        <span class="chip">Policy: <span id="fw-policy">-</span></span>
        <span class="chip">Active Connections: <span id="fw-count">0</span></span>
      </div>
      <table>
        <thead><tr><th>Type</th><th>User/Process</th><th>LAN IF</th><th>Local</th><th>Remote</th><th>Permission</th></tr></thead>
        <tbody id="fwflows"></tbody>
      </table>
    </div>

    <button class="btn" onclick="load()">Refresh</button>
    <div class="small">API: /api/status</div>

    <div class="card" style="margin-top:14px;">
      <div class="title">Details (Click Any Item Above)</div>
      <div id="detail-title" class="value">No item selected</div>
      <pre id="detail-body" style="white-space:pre-wrap; margin:10px 0 0; color:var(--muted); font-size:13px;"></pre>
    </div>
  </div>

<script>
function cls(v){ if(v==='active' || v==='running' || v===true) return 'ok'; if(v==='inactive' || v==='unknown') return 'warn'; return 'bad'; }
function text(v){ return (v===true)?'yes':(v===false)?'no':String(v); }
function esc(s){ return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;').replaceAll(\"'\",'&#39;'); }
async function showDetails(kind, name, label){
  const url = `/api/details?kind=${encodeURIComponent(kind)}&name=${encodeURIComponent(name || '')}`;
  const r = await fetch(url);
  const d = await r.json();
  document.getElementById('detail-title').textContent = label;
  document.getElementById('detail-body').textContent = d.details || 'No details';
}
async function load(){
  const r = await fetch('/api/status');
  const d = await r.json();
  document.getElementById('updated').textContent = d.timestamp;

  const top = [
    ['SSH', d.services.ssh.active, 'service', d.services.ssh.name],
    ['SMB', d.services.smb.active, 'smb', d.services.smb.name],
    ['Firewall (ufw)', d.services.ufw.status, 'ufw', 'ufw'],
    ['Internet', d.network.internet, 'internet', 'internet'],
  ];
  document.getElementById('top').innerHTML = top.map(([k,v,kind,name]) => `<div class="card clickable" onclick="showDetails('${esc(kind)}','${esc(name)}','${esc(k)}')"><div class="title">${k}</div><div class="value ${cls(v)}">${text(v)}</div></div>`).join('');

  document.getElementById('fetchers').innerHTML = d.custom_fetchers.map(s =>
    `<tr class="clickable" onclick="showDetails('service','${esc(s.name)}','Fetcher: ${esc(s.name)}')"><td>${s.name}</td><td class="${cls(s.active)}">${s.active}</td><td>${s.enabled}</td></tr>`).join('');

  document.getElementById('ifaces').innerHTML = d.network.interfaces.map(i =>
    `<tr class="clickable" onclick="showDetails('interface','${esc(i.name)}','Interface: ${esc(i.name)}')"><td>${i.name}</td><td class="${cls(i.state)}">${i.state}</td><td>${i.ip || '-'}</td></tr>`).join('');

  document.getElementById('users').innerHTML = d.users.map(u =>
    `<tr><td>${esc(u.user)}</td><td>${esc(u.kind)}</td><td>${esc(u.source)}</td><td>${esc(u.status)}</td></tr>`
  ).join('');

  document.getElementById('access').innerHTML = d.access_matrix.map(a =>
    `<tr><td>${esc(a.actor)}</td><td>${esc(a.resource)}</td><td>${esc(a.target)}</td><td>${esc(a.access)}</td></tr>`
  ).join('');

  document.getElementById('fw-policy').textContent = d.firewall_flow.policy;
  document.getElementById('fw-count').textContent = d.firewall_flow.total;
  document.getElementById('fwflows').innerHTML = d.firewall_flow.connections.map(c =>
    `<tr class="clickable" onclick="showDetails('connection','${esc(c.local + '->' + c.remote)}','Connection: ${esc(c.remote)}')"><td>${c.scope}</td><td>${esc(c.owner)}</td><td>${esc(c.interface)}</td><td>${esc(c.local)}</td><td>${esc(c.remote)}</td><td class="${cls(c.permission)}">${esc(c.permission)}</td></tr>`
  ).join('');
}
load();
</script>
</body>
</html>
"""


def run(cmd, include_stderr=False):
    p = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if include_stderr else subprocess.DEVNULL,
        text=True,
    )
    out = p.stdout.strip()
    if include_stderr and p.stderr.strip():
        out = (out + "\n" + p.stderr.strip()).strip()
    return out


def service_status(name):
    if not service_exists(name):
        return {"name": name, "active": "not-installed", "enabled": "not-installed"}
    active = run(f"systemctl is-active {name}") or "unknown"
    enabled = run(f"systemctl is-enabled {name}") or "unknown"
    return {"name": name, "active": active, "enabled": enabled}

def service_exists(name):
    return run(f"systemctl list-unit-files {name} --no-legend")

def first_service_status(candidates):
    for name in candidates:
        if service_exists(name):
            return service_status(name)
    return {"name": candidates[0], "active": "not-installed", "enabled": "not-installed"}


def ufw_status():
    if not shutil.which("ufw"):
        return "not-installed"
    out = run("ufw status | head -n1")
    if "inactive" in out.lower():
        return "inactive"
    if "active" in out.lower():
        return "active"
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
            flags = parts[2].split(">")[0]
            state_map[name] = "UP" if "UP" in flags else "DOWN"
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


def local_ipv4_addresses():
    return [row["ip"] for row in interfaces() if row["ip"]]


def listening_ports():
    out = run("ss -lntupH")
    rows = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        proto = parts[0]
        local = parts[4]
        proc = " ".join(parts[6:]) if len(parts) > 6 else ""
        rows.append({"proto": proto, "local": local, "process": proc})
    return rows


def firewall_policy_label():
    st = ufw_status()
    if st == "active":
        return "enforced"
    if st == "inactive":
        return "not-enforced"
    if st == "not-installed":
        return "not-installed"
    return "unknown"


def parse_ss_established():
    out = run("ss -tunpH state established", include_stderr=True)
    rows = []
    for line in out.splitlines():
        if not line or line.startswith("Netid"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        proto = parts[0]
        local = parts[3]
        remote = parts[4]
        proc = " ".join(parts[5:]) if len(parts) > 5 else ""
        rows.append({"proto": proto, "local": local, "remote": remote, "proc": proc})
    return rows


def route_interface_for_ip(ip_value):
    host = ip_value.rsplit(":", 1)[0].strip("[]")
    out = run(f"ip route get {host}", include_stderr=False)
    parts = out.split()
    if "dev" in parts:
        idx = parts.index("dev")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "unknown"


def scope_for_remote(remote):
    host = remote.rsplit(":", 1)[0].strip("[]")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return "local/internal"
        return "external"
    except ValueError:
        return "external"


def permission_hint(scope):
    policy = firewall_policy_label()
    if policy == "enforced":
        return "allowed-by-rules"
    if policy in ("not-enforced", "not-installed"):
        return "allowed-unrestricted"
    return "unknown"


def connection_owner(proc):
    if not proc:
        return "unresolved"
    return proc.replace('users:(("', "").replace('"))', "")


def current_users():
    users = []
    for line in run("who").splitlines():
        p = line.split()
        if p:
            users.append({"user": p[0], "kind": "shell", "source": p[1] if len(p) > 1 else "-", "status": "logged-in"})
    smb = run("smbstatus -b", include_stderr=True)
    for line in smb.splitlines():
        if "smbd version" in line.lower() or "pid" in line.lower():
            continue
        p = line.split()
        if len(p) >= 2 and p[0].isdigit():
            users.append({"user": p[1], "kind": "smb", "source": "samba", "status": "connected"})
    if not users:
        users.append({"user": "none", "kind": "system", "source": "-", "status": "no-active-user"})
    return users


def parse_smb_shares():
    conf = run("testparm -s", include_stderr=True)
    shares = []
    current = None
    for raw in conf.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            if name and name.lower() != "global":
                current = {"share": name, "path": "-", "users": "all", "access": "read-only"}
                shares.append(current)
            else:
                current = None
            continue
        if not current or "=" not in line:
            continue
        k, v = [x.strip() for x in line.split("=", 1)]
        if k == "path":
            current["path"] = v
        elif k == "valid users":
            current["users"] = v
        elif k == "read only":
            current["access"] = "read-only" if v.lower() in ("yes", "true") else "read-write"
    return shares


def access_matrix():
    rows = []
    for c in firewall_flow()["connections"][:120]:
        rows.append({
            "actor": c["owner"],
            "resource": "network",
            "target": c["remote"],
            "access": c["permission"],
        })
    for s in parse_smb_shares():
        rows.append({
            "actor": s["users"],
            "resource": f"smb-share:{s['share']}",
            "target": s["path"],
            "access": s["access"],
        })
    if not rows:
        rows.append({"actor": "none", "resource": "none", "target": "-", "access": "no-data"})
    return rows


def firewall_flow():
    conns = parse_ss_established()
    rows = []
    for c in conns:
        scope = scope_for_remote(c["remote"])
        rows.append({
            "scope": scope,
            "owner": connection_owner(c["proc"]),
            "interface": route_interface_for_ip(c["remote"]),
            "local": c["local"],
            "remote": c["remote"],
            "permission": permission_hint(scope),
        })
    rows.sort(key=lambda x: (0 if x["scope"] == "external" else 1, x["remote"]))
    return {
        "policy": firewall_policy_label(),
        "total": len(rows),
        "connections": rows[:120],
    }


@app.route("/")
def index():
    return render_template_string(TEMPLATE, host=socket.gethostname())


@app.route("/api/status")
def api_status():
    ssh = first_service_status(["ssh.service", "sshd.service"])
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
        "firewall_flow": firewall_flow(),
        "users": current_users(),
        "access_matrix": access_matrix(),
    }
    return jsonify(data)


@app.route("/api/details")
def api_details():
    kind = request.args.get("kind", "")
    name = request.args.get("name", "")

    if kind == "service":
        details = run(f"systemctl status {name} --no-pager -n 20")
        if not details:
            details = f"No data for service: {name}"
        return jsonify({"details": details})

    if kind == "interface":
        details = []
        details.append(run(f"ip addr show dev {name}"))
        details.append(run(f"ip -s link show dev {name}"))
        details.append(run(f"ip route | rg -n \"{name}\"") if shutil.which("rg") else run(f"ip route | grep -n \"{name}\""))
        return jsonify({"details": "\n\n".join([d for d in details if d]) or f"No data for interface: {name}"})

    if kind == "ufw":
        chunks = []
        if shutil.which("ufw"):
            chunks.append("$ ufw status verbose\n" + run("ufw status verbose", include_stderr=True))
            chunks.append("$ ufw status numbered\n" + run("ufw status numbered", include_stderr=True))
            chunks.append("$ ufw show raw\n" + run("ufw show raw", include_stderr=True))
        else:
            chunks.append("ufw not installed")
        chunks.append("$ nft list ruleset\n" + (run("nft list ruleset", include_stderr=True) or "No nft output"))
        chunks.append("$ iptables -S\n" + (run("iptables -S", include_stderr=True) or "No iptables output"))
        ports = listening_ports()
        chunks.append(f"Listening ports count: {len(ports)}")
        chunks.append("\n".join([f"{p['proto']} {p['local']} {p['process']}" for p in ports[:50]]) or "No listening ports found")
        chunks.append("$ ss -tunp state established\n" + (run("ss -tunp state established", include_stderr=True) or "No established connections"))
        return jsonify({"details": "\n\n".join(chunks)})

    if kind == "smb":
        chunks = []
        chunks.append("$ systemctl status smbd.service --no-pager -n 30\n" + (run("systemctl status smbd.service --no-pager -n 30", include_stderr=True) or "No output"))
        chunks.append("$ testparm -s\n" + (run("testparm -s", include_stderr=True) or "testparm not available or no output"))
        chunks.append("$ net usershare list\n" + (run("net usershare list", include_stderr=True) or "No usershares"))
        usershares = run("net usershare list", include_stderr=False).splitlines()
        if usershares:
            details = []
            for share in usershares:
                share = share.strip()
                if share:
                    details.append(f"$ net usershare info '{share}'\n" + run(f"net usershare info '{share}'", include_stderr=True))
            if details:
                chunks.append("\n\n".join(details))
        chunks.append("$ smbstatus -S\n" + (run("smbstatus -S", include_stderr=True) or "No active SMB sessions"))
        chunks.append("$ smbstatus -L\n" + (run("smbstatus -L", include_stderr=True) or "No SMB locks"))
        return jsonify({"details": "\n\n".join(chunks)})

    if kind == "internet":
        checks = [
            "ping -c 2 1.1.1.1",
            "ping -c 2 google.com",
            "getent hosts google.com",
            "ip route show default",
        ]
        out = []
        out.append("Local IPv4:\n" + ("\n".join(local_ipv4_addresses()) or "No IPv4 found"))
        ports = listening_ports()
        out.append(f"Listening ports: {len(ports)}")
        out.append("\n".join([f"{p['proto']} {p['local']} {p['process']}" for p in ports[:50]]) or "No listening ports found")
        for c in checks:
            out.append(f"$ {c}\n{run(c)}")
        out.append("$ ss -tun state established | head -n 30\n" + run("ss -tun state established | head -n 30"))
        return jsonify({"details": "\n\n".join(out)})

    return jsonify({"details": "Unknown detail type"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9080)
