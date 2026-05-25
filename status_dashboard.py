#!/usr/bin/env python3
import os
import shutil
import socket
import subprocess
import ipaddress
from datetime import datetime
from datetime import timedelta

from flask import Flask, jsonify, render_template_string
from flask import request
from flask import session

app = Flask(__name__)
os.environ["PATH"] = os.environ.get("PATH", "") + ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
app.secret_key = os.environ.get("LINUXMONITOR_SECRET", "change-this-secret")
app.permanent_session_lifetime = timedelta(minutes=10)

# Put your custom service names here.
CUSTOM_FETCHERS = [
    "fetcher-a.service",
    "fetcher-b.service",
]
DEFAULT_ALLOWED_DOMAINS_FILE = "/home/comp5/work/git/LinuxMonitor/allowed_domains.txt"
ADMIN_ACTIONS = {
    "restart_dashboard": "systemctl restart pc-status-dashboard",
    "restart_ssh": "systemctl restart ssh",
    "restart_smb": "systemctl restart smbd",
    "ufw_reload": "ufw reload",
    "ufw_enable": "ufw --force enable",
    "ufw_disable": "ufw disable",
}

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
        <thead><tr><th>User/Process</th><th>Resource</th><th>Path/Target</th><th>Network</th><th>Access</th></tr></thead>
        <tbody id="access"></tbody>
      </table>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="title"><span class="ico">%</span>Router URL Policy</div>
      <div style="margin-bottom:8px;" class="small">Allowed domains file: <span id="rules-file">{{ allowed_file }}</span></div>
      <div style="margin-bottom:8px;" class="small" id="rules-meta">-</div>
      <div style="margin-bottom:8px;" class="small">Allowed domains: <span id="rules-domains">-</span></div>
      <div style="display:flex; gap:8px; margin-bottom:10px;">
        <input id="rule-domain" placeholder="example.com" style="flex:1; background:#0f1b30; color:#e8eef9; border:1px solid #284267; border-radius:8px; padding:8px;" />
        <button class="btn" style="margin-top:0;" onclick="ruleAdd()">Add</button>
        <button class="btn" style="margin-top:0;" onclick="ruleRemove()">Remove</button>
        <button class="btn" style="margin-top:0;" onclick="load()">Refresh</button>
      </div>
      <div id="rule-msg" class="small"></div>
      <table>
        <thead><tr><th>Remote</th><th>Resolved Host</th><th>Policy</th><th>Route IF</th></tr></thead>
        <tbody id="router"></tbody>
      </table>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="title"><span class="ico">!</span>Admin (sudo in browser, auto logout)</div>
      <div style="display:flex; gap:8px; margin-bottom:10px;">
        <input id="sudo-pass" type="password" placeholder="sudo password" style="flex:1; background:#0f1b30; color:#e8eef9; border:1px solid #284267; border-radius:8px; padding:8px;" />
        <button class="btn" style="margin-top:0;" onclick="adminLogin()">Login</button>
        <button class="btn" style="margin-top:0;" onclick="adminLogout()">Logout</button>
      </div>
      <div id="admin-state" class="small">Admin: logged-out</div>
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;">
        <button class="btn" style="margin-top:0;" onclick="adminRun('restart_dashboard')">Restart Dashboard</button>
        <button class="btn" style="margin-top:0;" onclick="adminRun('restart_ssh')">Restart SSH</button>
        <button class="btn" style="margin-top:0;" onclick="adminRun('restart_smb')">Restart SMB</button>
        <button class="btn" style="margin-top:0;" onclick="adminRun('ufw_reload')">UFW Reload</button>
        <button class="btn" style="margin-top:0;" onclick="adminRun('ufw_enable')">UFW Enable</button>
        <button class="btn" style="margin-top:0;" onclick="adminRun('ufw_disable')">UFW Disable</button>
      </div>
      <pre id="admin-out" style="white-space:pre-wrap; margin:10px 0 0; color:var(--muted); font-size:13px;"></pre>
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

  </div>

<script>
function cls(v){ if(v==='active' || v==='running' || v===true) return 'ok'; if(v==='inactive' || v==='unknown') return 'warn'; return 'bad'; }
function text(v){ return (v===true)?'yes':(v===false)?'no':String(v); }
function esc(s){ return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;').replaceAll(\"'\",'&#39;'); }
function goDetail(kind, name, label){
  const url = `/view?kind=${encodeURIComponent(kind)}&name=${encodeURIComponent(name || '')}&label=${encodeURIComponent(label || '')}`;
  window.location.href = url;
}
async function changeRule(action){
  const domain = document.getElementById('rule-domain').value.trim().toLowerCase();
  const r = await fetch('/api/router/rules', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({action, domain})
  });
  const d = await r.json();
  document.getElementById('rule-msg').textContent = d.message || 'done';
  await load();
}
async function ruleAdd(){ await changeRule('add'); }
async function ruleRemove(){ await changeRule('remove'); }
async function adminStatus(){
  const r = await fetch('/api/admin/status');
  const d = await r.json();
  document.getElementById('admin-state').textContent = d.active ? `Admin: logged-in (expires ${d.expires_in}s)` : 'Admin: logged-out';
}
async function adminLogin(){
  const password = document.getElementById('sudo-pass').value;
  const r = await fetch('/api/admin/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({password})});
  const d = await r.json();
  document.getElementById('admin-out').textContent = d.message || '';
  await adminStatus();
}
async function adminLogout(){
  const r = await fetch('/api/admin/logout', {method:'POST'});
  const d = await r.json();
  document.getElementById('admin-out').textContent = d.message || '';
  await adminStatus();
}
async function adminRun(action){
  const r = await fetch('/api/admin/run', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action})});
  const d = await r.json();
  document.getElementById('admin-out').textContent = d.output || d.message || '';
  await adminStatus();
  await load();
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
  document.getElementById('top').innerHTML = top.map(([k,v,kind,name]) => `<div class="card clickable" onclick="goDetail('${esc(kind)}','${esc(name)}','${esc(k)}')"><div class="title">${k}</div><div class="value ${cls(v)}">${text(v)}</div></div>`).join('');

  document.getElementById('fetchers').innerHTML = d.custom_fetchers.map(s =>
    `<tr class="clickable" onclick="goDetail('service','${esc(s.name)}','Fetcher: ${esc(s.name)}')"><td>${s.name}</td><td class="${cls(s.active)}">${s.active}</td><td>${s.enabled}</td></tr>`).join('');

  document.getElementById('ifaces').innerHTML = d.network.interfaces.map(i =>
    `<tr class="clickable" onclick="goDetail('interface','${esc(i.name)}','Interface: ${esc(i.name)}')"><td>${i.name}</td><td class="${cls(i.state)}">${i.state}</td><td>${i.ip || '-'}</td></tr>`).join('');

  document.getElementById('users').innerHTML = d.users.map(u =>
    `<tr><td>${esc(u.user)}</td><td>${esc(u.kind)}</td><td>${esc(u.source)}</td><td>${esc(u.status)}</td></tr>`
  ).join('');

  document.getElementById('access').innerHTML = d.access_matrix.map(a =>
    `<tr><td>${esc(a.actor)}</td><td>${esc(a.resource)}</td><td>${esc(a.target)}</td><td>${esc(a.network || '-')}</td><td>${esc(a.access)}</td></tr>`
  ).join('');
  document.getElementById('router').innerHTML = d.router_policy.connections.map(r =>
    `<tr class="clickable" onclick="goDetail('connection','${esc(r.remote)}','Router Peer: ${esc(r.host)}')"><td>${esc(r.remote)}</td><td>${esc(r.host)}</td><td class="${cls(r.policy)}">${esc(r.policy)}</td><td>${esc(r.interface)}</td></tr>`
  ).join('');
  const sm = d.router_policy.settings || {};
  document.getElementById('rules-file').textContent = sm.file || '-';
  document.getElementById('rules-meta').textContent = `exists=${sm.exists} | rules=${sm.rules_count} | updated=${sm.updated_at || '-'}`;
  document.getElementById('rules-domains').textContent = (d.router_policy.allowed_domains || []).join(', ') || 'none';

  document.getElementById('fw-policy').textContent = d.firewall_flow.policy;
  document.getElementById('fw-count').textContent = d.firewall_flow.total;
  document.getElementById('fwflows').innerHTML = d.firewall_flow.connections.map(c =>
    `<tr class="clickable" onclick="goDetail('connection','${esc(c.remote)}','Connection: ${esc(c.remote)}')"><td>${c.scope}</td><td>${esc(c.owner)}</td><td>${esc(c.interface)}</td><td>${esc(c.local)}</td><td>${esc(c.remote)}</td><td class="${cls(c.permission)}">${esc(c.permission)}</td></tr>`
  ).join('');
}
load();
adminStatus();
</script>
</body>
</html>
"""

DETAIL_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{{ label or 'Detail' }}</title>
  <style>
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background:#0b1320; color:#e8eef9; }
    .wrap { max-width: 1100px; margin: 20px auto; padding: 0 16px; }
    .bar { display:flex; gap:10px; align-items:center; }
    .btn { background:#22406b; color:#fff; border:0; border-radius:8px; padding:8px 12px; cursor:pointer; }
    .muted { color:#9ab0d3; font-size: 13px; }
    .card { background:#132038; border:1px solid #284267; border-radius:12px; padding:14px; margin-top:12px; }
    pre { white-space:pre-wrap; margin:0; font-size:13px; color:#cfe0fb; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="bar">
      <button class="btn" onclick="window.location.href='/'">Back</button>
      <button class="btn" onclick="load()">Refresh</button>
      <h2 style="margin:0;">{{ label or 'Detail' }}</h2>
    </div>
    <div class="muted">kind={{ kind }} | name={{ name }}</div>
    <div class="card"><pre id="detail">Loading...</pre></div>
  </div>
<script>
async function load(){
  const url = `/api/details?kind={{ kind | urlencode }}&name={{ name | urlencode }}`;
  const r = await fetch(url);
  const d = await r.json();
  document.getElementById('detail').textContent = d.details || 'No details';
}
load();
setInterval(load, 10000);
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


def allowed_domains_file():
    return os.environ.get("LINUXMONITOR_ALLOWED_DOMAINS_FILE", DEFAULT_ALLOWED_DOMAINS_FILE)


def run_with_rc(cmd):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


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


def parse_smb_sessions():
    out = run("smbstatus -p", include_stderr=True)
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("smbstatus") or line.startswith("PID") or line.startswith("-"):
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            rows.append({
                "pid": parts[0],
                "user": parts[1],
                "group": parts[2],
                "machine": parts[3],
            })
    return rows


def access_matrix():
    rows = []
    for c in firewall_flow()["connections"][:120]:
        rows.append({
            "actor": c["owner"],
            "resource": "network",
            "target": c["remote"],
            "network": c.get("interface", "-"),
            "access": c["permission"],
        })
    for s in parse_smb_shares():
        rows.append({
            "actor": s["users"],
            "resource": f"smb-share:{s['share']}",
            "target": s["path"],
            "network": "smb (configured)",
            "access": s["access"],
        })
    for sess in parse_smb_sessions():
        machine = sess["machine"].replace("(", "").replace(")", "")
        iface = route_interface_for_ip(machine if ":" in machine else f"{machine}:445")
        rows.append({
            "actor": sess["user"],
            "resource": "smb-session",
            "target": machine,
            "network": iface,
            "access": "active-session",
        })
    if not rows:
        rows.append({"actor": "none", "resource": "none", "target": "-", "network": "-", "access": "no-data"})
    return rows


def load_allowed_domains():
    path = allowed_domains_file()
    if not os.path.exists(path):
        return []
    domains = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip().lower()
            if not line or line.startswith("#"):
                continue
            domains.append(line)
    return domains


def save_allowed_domains(domains):
    uniq = sorted(set([d.strip().lower() for d in domains if d.strip()]))
    with open(allowed_domains_file(), "w", encoding="utf-8") as f:
        f.write("# One domain per line\n")
        for d in uniq:
            f.write(d + "\n")


def reverse_host(ip_or_host):
    host = ip_or_host.rsplit(":", 1)[0].strip("[]")
    out = run(f"getent hosts {host}")
    if not out:
        return host
    parts = out.split()
    return parts[1] if len(parts) > 1 else host


def host_allowed(host, allowed):
    h = host.lower()
    for d in allowed:
        if h == d or h.endswith("." + d):
            return True
    return False


def router_policy():
    allowed = load_allowed_domains()
    fpath = allowed_domains_file()
    exists = os.path.exists(fpath)
    updated_at = None
    if exists:
        updated_at = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for c in firewall_flow()["connections"]:
        if c["scope"] != "external":
            continue
        host = reverse_host(c["remote"])
        policy = "allowed" if allowed and host_allowed(host, allowed) else "not-in-allowlist"
        if not allowed:
            policy = "no-allowlist-configured"
        rows.append({
            "remote": c["remote"],
            "host": host,
            "policy": policy,
            "interface": c["interface"],
        })
    return {
        "allowed_domains": allowed,
        "connections": rows[:120],
        "settings": {
            "file": fpath,
            "exists": exists,
            "rules_count": len(allowed),
            "updated_at": updated_at,
        },
    }


def admin_active():
    exp = session.get("admin_exp")
    if not exp:
        return False
    return datetime.now().timestamp() < exp


def require_admin():
    if not admin_active():
        return jsonify({"ok": False, "message": "Admin login required"}), 403
    session["admin_exp"] = (datetime.now() + timedelta(minutes=10)).timestamp()
    return None


@app.route("/api/router/rules", methods=["POST"])
def router_rules():
    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").strip().lower()
    domain = (payload.get("domain") or "").strip().lower()

    if action == "refresh":
        return jsonify({"ok": True, "message": "Rules refreshed", "domains": load_allowed_domains()})

    if not domain or "." not in domain:
        return jsonify({"ok": False, "message": "Provide valid domain, e.g. example.com"}), 400

    domains = load_allowed_domains()
    if action == "add":
        domains.append(domain)
        save_allowed_domains(domains)
        return jsonify({"ok": True, "message": f"Added: {domain}", "domains": load_allowed_domains()})
    if action == "remove":
        domains = [d for d in domains if d != domain]
        save_allowed_domains(domains)
        return jsonify({"ok": True, "message": f"Removed: {domain}", "domains": load_allowed_domains()})

    return jsonify({"ok": False, "message": "Unsupported action"}), 400


@app.route("/api/admin/status")
def admin_status():
    active = admin_active()
    left = 0
    if active:
        left = int(session.get("admin_exp", 0) - datetime.now().timestamp())
    return jsonify({"active": active, "expires_in": max(0, left)})


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    payload = request.get_json(silent=True) or {}
    password = payload.get("password", "")
    if not password:
        return jsonify({"ok": False, "message": "Password required"}), 400
    p = subprocess.run(
        ["sudo", "-S", "-k", "-v"],
        input=password + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if p.returncode != 0:
        return jsonify({"ok": False, "message": "sudo auth failed", "output": (p.stdout + "\n" + p.stderr).strip()}), 403
    session.permanent = True
    session["admin_exp"] = (datetime.now() + timedelta(minutes=10)).timestamp()
    return jsonify({"ok": True, "message": "Admin login success. Auto logout: 10 minutes inactivity."})


@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_exp", None)
    return jsonify({"ok": True, "message": "Admin logged out"})


@app.route("/api/admin/run", methods=["POST"])
def admin_run():
    guard = require_admin()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").strip()
    cmd = ADMIN_ACTIONS.get(action)
    if not cmd:
        return jsonify({"ok": False, "message": "Unsupported admin action"}), 400
    rc, out, err = run_with_rc(f"sudo -n {cmd}")
    return jsonify({"ok": rc == 0, "message": "done" if rc == 0 else "failed", "output": (out + "\n" + err).strip()})


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
    return render_template_string(TEMPLATE, host=socket.gethostname(), allowed_file=allowed_domains_file())


@app.route("/view")
def view_page():
    kind = request.args.get("kind", "service")
    name = request.args.get("name", "")
    label = request.args.get("label", "")
    return render_template_string(DETAIL_TEMPLATE, kind=kind, name=name, label=label)


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
        "router_policy": router_policy(),
    }
    return jsonify(data)


@app.route("/api/details")
def api_details():
    kind = request.args.get("kind", "")
    name = request.args.get("name", "")

    if kind == "service":
        parts = []
        parts.append("[Status]\n" + (run(f"systemctl status {name} --no-pager -n 20") or "No status output"))
        parts.append("[Enabled]\n" + (run(f"systemctl is-enabled {name}", include_stderr=True) or "unknown"))
        parts.append("[Recent Logs]\n" + (run(f"journalctl -u {name} -n 40 --no-pager") or "No logs"))
        details = "\n\n".join(parts)
        if not details:
            details = f"No data for service: {name}"
        return jsonify({"details": details})

    if kind == "interface":
        details = []
        details.append("[Address]\n" + run(f"ip addr show dev {name}"))
        details.append("[Stats]\n" + run(f"ip -s link show dev {name}"))
        details.append("[Routes]\n" + (run(f"ip route | rg -n \"{name}\"") if shutil.which("rg") else run(f"ip route | grep -n \"{name}\"")))
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

    if kind == "connection":
        target = name.strip()
        cmds = [
            f"ss -tunp | rg -n \"{target}\"" if shutil.which("rg") else f"ss -tunp | grep -n \"{target}\"",
            "ss -tunp state established",
            "ip route show",
        ]
        out = []
        out.append("[Connection Match]")
        out.append(run(cmds[0], include_stderr=True) or f"No direct matches for {target}")
        out.append("\n[Established Snapshot]")
        out.append(run(cmds[1], include_stderr=True) or "No established connections")
        out.append("\n[Routing]")
        out.append(run(cmds[2], include_stderr=True) or "No route output")
        return jsonify({"details": "\n".join(out)})

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
