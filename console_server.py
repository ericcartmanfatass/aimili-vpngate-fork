#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import random
import string
import subprocess
import time
import urllib.parse
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(os.environ.get("AIMILIVPN_CONFIG_DIR", "/etc/aimilivpn"))
INSTALL_DIR = Path(os.environ.get("AIMILIVPN_INSTALL_DIR", "/opt/aimilivpn"))
AUTH_FILE = Path(os.environ.get("AIMILIVPN_CONSOLE_AUTH", str(CONFIG_DIR / "console_auth.json")))
INSTANCES_FILE = Path(os.environ.get("AIMILIVPN_INSTANCES_FILE", str(CONFIG_DIR / "instances.json")))
CONSOLE_HOST = os.environ.get("CONSOLE_HOST", "0.0.0.0")
CONSOLE_PORT = int(os.environ.get("CONSOLE_PORT", "8788"))

sessions: dict[str, float] = {}


def random_token(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_console_auth() -> dict[str, Any]:
    cfg = {
        "username": "admin",
        "password": "",
        "secret_path": "console" + random_token(8),
        "host": CONSOLE_HOST,
        "port": CONSOLE_PORT,
    }
    data = read_json(AUTH_FILE, {})
    if isinstance(data, dict):
        cfg.update(data)
    changed = False
    if not cfg.get("username"):
        cfg["username"] = "admin"
        changed = True
    if not cfg.get("password"):
        cfg["password"] = random_token(16)
        changed = True
    if not cfg.get("secret_path"):
        cfg["secret_path"] = "console" + random_token(8)
        changed = True
    if changed or not AUTH_FILE.exists():
        write_json(AUTH_FILE, cfg)
        try:
            AUTH_FILE.chmod(0o600)
        except OSError:
            pass
    return cfg


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def normalize_instance(item: dict[str, Any]) -> dict[str, Any]:
    iid = str(item.get("id") or item.get("instance_id") or item.get("country") or "").lower()
    env_file = Path(str(item.get("env_file") or CONFIG_DIR / f"{iid}.env"))
    env = parse_env_file(env_file)
    country = str(item.get("country") or env.get("ALLOWED_COUNTRIES") or iid).upper()
    data_dir = str(item.get("data_dir") or env.get("VPNGATE_DATA_DIR") or INSTALL_DIR / "data" / iid)
    ui_port = int(item.get("ui_port") or env.get("UI_PORT") or 0)
    proxy_port = int(item.get("proxy_port") or env.get("LOCAL_PROXY_PORT") or 0)
    auth = read_json(Path(data_dir) / "ui_auth.json", {})
    secret = str(auth.get("secret_path") or "EJsW2EeBo9lY")
    return {
        "id": iid,
        "country": country,
        "service": str(item.get("service") or f"aimilivpn@{iid}.service"),
        "env_file": str(env_file),
        "data_dir": data_dir,
        "ui_host": str(item.get("ui_host") or env.get("UI_HOST") or "127.0.0.1"),
        "ui_port": ui_port,
        "proxy_host": str(item.get("proxy_host") or env.get("LOCAL_PROXY_HOST") or "127.0.0.1"),
        "proxy_port": proxy_port,
        "tun_dev": str(item.get("tun_dev") or env.get("TUN_DEV") or ""),
        "policy_table": str(item.get("policy_table") or env.get("POLICY_TABLE") or ""),
        "secret_path": secret,
    }


def load_instances() -> list[dict[str, Any]]:
    data = read_json(INSTANCES_FILE, {})
    raw_instances = data.get("instances") if isinstance(data, dict) else None
    if isinstance(raw_instances, list) and raw_instances:
        return [normalize_instance(item) for item in raw_instances if isinstance(item, dict)]

    instances = []
    for env_file in sorted(CONFIG_DIR.glob("*.env")):
        iid = env_file.stem.lower()
        instances.append(normalize_instance({"id": iid, "env_file": str(env_file)}))
    return instances


def instance_by_id(instance_id: str) -> dict[str, Any] | None:
    target = instance_id.lower()
    for inst in load_instances():
        if inst["id"] == target:
            return inst
    return None


def systemctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl"] + args, capture_output=True, text=True, timeout=10)


def service_active(service: str) -> bool:
    try:
        return systemctl(["is-active", "--quiet", service]).returncode == 0
    except Exception:
        return False


def service_action(service: str, action: str) -> dict[str, Any]:
    if action not in {"start", "stop", "restart"}:
        return {"ok": False, "error": "unsupported service action"}
    try:
        res = systemctl([action, service])
        return {
            "ok": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def instance_state(inst: dict[str, Any]) -> dict[str, Any]:
    data_dir = Path(inst["data_dir"])
    state = read_json(data_dir / "state.json", {})
    nodes = read_json(data_dir / "nodes.json", [])
    active_id = state.get("active_openvpn_node_id", "")
    active_node = None
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("id") == active_id:
                active_node = {
                    "id": node.get("id"),
                    "ip": node.get("ip") or node.get("remote_host"),
                    "country": node.get("country"),
                    "latency_ms": node.get("latency_ms"),
                    "quality": node.get("quality"),
                }
                break
    return {
        "id": inst["id"],
        "country": inst["country"],
        "service": inst["service"],
        "service_active": service_active(inst["service"]),
        "data_dir": inst["data_dir"],
        "ui_port": inst["ui_port"],
        "proxy_port": inst["proxy_port"],
        "tun_dev": inst["tun_dev"],
        "policy_table": inst["policy_table"],
        "local_proxy": f"socks5://127.0.0.1:{inst['proxy_port']}",
        "state": state if isinstance(state, dict) else {},
        "active_node": active_node,
    }


def backend_request(inst: dict[str, Any], api_path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = os.environ.get("INSTANCE_API_TOKEN", "")
    path = api_path
    body = None
    headers = {"X-Aimili-Console-Token": token}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    conn = http.client.HTTPConnection("127.0.0.1", int(inst["ui_port"]), timeout=12)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
    except Exception as exc:
        return {
            "ok": False,
            "status": 502,
            "error": f"backend {inst['id']} unavailable on 127.0.0.1:{inst['ui_port']}: {exc}",
        }
    finally:
        conn.close()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = {"raw": raw.decode("utf-8", errors="replace")}
    if resp.status >= 400:
        return {"ok": False, "status": resp.status, "error": data}
    return data if isinstance(data, dict) else {"ok": True, "data": data}


def stripped_nodes(inst: dict[str, Any]) -> dict[str, Any]:
    nodes = read_json(Path(inst["data_dir"]) / "nodes.json", [])
    clean = []
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            item = dict(node)
            item.pop("config_text", None)
            clean.append(item)
    return {"nodes": clean, "state": instance_state(inst)}


def read_logs(inst: dict[str, Any]) -> dict[str, Any]:
    logs_dir = Path(inst["data_dir"]) / "logs"
    today = time.strftime("%Y-%m-%d", time.localtime())
    log_file = logs_dir / f"{today}.json"
    entries = []
    if log_file.exists():
        try:
            for line in log_file.read_text(encoding="utf-8").splitlines()[-300:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        except OSError:
            pass
    return {"logs": entries}


LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AimiliVPN Console Login</title>
<style>
body{margin:0;background:#101318;color:#eef2f7;font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh}
form{width:min(360px,calc(100vw - 32px));background:#171c24;border:1px solid #2b3442;border-radius:8px;padding:24px}
h1{font-size:22px;margin:0 0 18px}label{display:block;font-size:13px;color:#aab4c3;margin:12px 0 6px}
input,button{box-sizing:border-box;width:100%;height:42px;border-radius:6px}input{background:#0f141b;border:1px solid #334155;color:#fff;padding:0 12px}
button{margin-top:18px;border:0;background:#2f8cff;color:#fff;font-weight:700;cursor:pointer}.err{color:#ff7b7b;min-height:20px;font-size:13px}
</style></head><body>
<form onsubmit="login(event)"><h1>AimiliVPN Console</h1><div class="err" id="err"></div>
<label>Username</label><input id="u" autocomplete="username" required>
<label>Password</label><input id="p" type="password" autocomplete="current-password" required>
<button>Login</button></form>
<script>
async function login(e){e.preventDefault();err.textContent='';const r=await fetch('./api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})});if(r.ok){location.reload()}else{err.textContent='Login failed'}}
</script></body></html>"""


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AimiliVPN Console</title>
<style>
:root{color-scheme:dark;--bg:#0e1116;--panel:#151a22;--line:#293241;--muted:#96a3b4;--text:#eef2f7;--blue:#2f8cff;--green:#35c486;--red:#ff6969}
body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif}
header{height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid var(--line);background:#11161d;position:sticky;top:0}
h1{font-size:18px;margin:0}.wrap{display:grid;grid-template-columns:300px 1fr;min-height:calc(100vh - 57px)}
aside{border-right:1px solid var(--line);background:#121720;padding:14px}.inst{display:grid;gap:8px}
button{border:1px solid var(--line);background:#1b2230;color:var(--text);border-radius:6px;height:34px;padding:0 12px;cursor:pointer}
button.primary{background:var(--blue);border-color:var(--blue);color:#fff}button.danger{background:#3a1d22;border-color:#6c2a34}
.card{border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:14px;margin-bottom:14px}.row{display:flex;align-items:center;justify-content:space-between;gap:8px}
.pill{font-size:12px;border-radius:999px;padding:3px 8px;background:#222b38;color:var(--muted)}.ok{color:var(--green)}.bad{color:var(--red)}.muted{color:var(--muted)}
main{padding:16px;overflow:auto}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.tab.active{background:var(--blue);border-color:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;border-bottom:1px solid var(--line);padding:9px 8px;vertical-align:middle}th{color:var(--muted);font-weight:600}
pre{white-space:pre-wrap;max-height:260px;overflow:auto;background:#0b0f14;border:1px solid var(--line);border-radius:6px;padding:10px}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
@media(max-width:820px){.wrap{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body>
<header><h1>AimiliVPN Console</h1><button onclick="logout()">Logout</button></header>
<div class="wrap"><aside><div class="inst" id="instances"></div></aside><main>
<div class="tabs"><button class="tab active" id="tabOverview" onclick="showOverview()">Overview</button><span id="instanceTabs"></span></div>
<section id="content"></section></main></div>
<script>
let instanceList=[], current=null;
async function api(path, opts){const r=await fetch('./api/'+path, opts); const text=await r.text(); let data={}; try{data=text?JSON.parse(text):{};}catch(e){data={raw:text};} if(!r.ok || data.ok===false){throw new Error(typeof data.error==='string'?data.error:JSON.stringify(data.error||data));} return data;}
function esc(v){return String(v ?? '').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function el(id){return document.getElementById(id)}
function showError(msg){el('content').insertAdjacentHTML('afterbegin',`<div class="card bad"><b>Operation failed</b><div>${esc(msg)}</div></div>`)}
function statusText(i){return i.service_active?'<span class="ok">running</span>':'<span class="bad">stopped</span>'}
async function load(){instanceList=(await api('instances')).instances; renderSide(); showOverview();}
function renderSide(){const instancesEl=instanceList.map(i=>`<div class="card"><div class="row"><b>${esc(i.country)}</b><span class="pill">${esc(i.id)}</span></div><div class="muted">Proxy ${esc(i.proxy_port)} · ${esc(i.tun_dev)}</div><div>${statusText(i)}</div><div class="toolbar"><button onclick="openInst('${i.id}')">Open</button><button onclick="svc('${i.id}','restart')">Restart</button></div></div>`).join('');el('instances').innerHTML=instancesEl;el('instanceTabs').innerHTML=instanceList.map(i=>`<button class="tab" onclick="openInst('${i.id}')">${esc(i.country)}</button>`).join(' ');}
function showOverview(){current=null;document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));el('tabOverview').classList.add('active');el('content').innerHTML=`<div class="card"><h2>Overview</h2><table><thead><tr><th>Country</th><th>Service</th><th>Proxy</th><th>TUN</th><th>Active node</th><th>Message</th><th>Action</th></tr></thead><tbody>${instanceList.map(i=>`<tr><td>${esc(i.country)}</td><td>${statusText(i)}</td><td>${esc(i.local_proxy)}</td><td>${esc(i.tun_dev)}</td><td>${esc(i.active_node?.ip||'-')}</td><td>${esc(i.state?.last_check_message||'')}</td><td><button onclick="openInst('${i.id}')">Manage</button></td></tr>`).join('')}</tbody></table></div>`}
async function openInst(id){current=id;document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));const data=await api(`instances/${id}/nodes`);const i=data.state;el('content').innerHTML=`<div class="card"><div class="row"><div><h2>${esc(i.country)} <span class="pill">${esc(id)}</span></h2><div class="muted">${esc(i.local_proxy)} · ${esc(i.tun_dev)} · table ${esc(i.policy_table)}</div></div><div>${statusText(i)}</div></div><div class="toolbar"><button class="primary" onclick="post('${id}','refresh_nodes')">Refresh nodes</button><button onclick="post('${id}','test_proxy')">Test proxy</button><button onclick="post('${id}','disconnect')">Disconnect</button><button onclick="svc('${id}','restart')">Restart service</button><button onclick="logs('${id}')">Logs</button></div></div><div class="card"><table><thead><tr><th>Status</th><th>IP</th><th>Country</th><th>Latency</th><th>Quality</th><th>Action</th></tr></thead><tbody>${data.nodes.map(n=>`<tr><td>${n.active?'<span class="ok">active</span>':esc(n.probe_status||'-')}</td><td>${esc(n.ip||n.remote_host)}</td><td>${esc(n.country||n.country_short)}</td><td>${esc(n.latency_ms||n.ping||'-')}</td><td>${esc(n.quality||'-')}</td><td><button onclick="connect('${id}','${esc(n.id)}')">Connect</button><button onclick="testNode('${id}','${esc(n.id)}')">Test</button></td></tr>`).join('')}</tbody></table></div>`}
async function svc(id,action){try{await api(`instances/${id}/service`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})}); await load();}catch(e){showError(e.message)}}
async function post(id,action){try{await api(`instances/${id}/${action}`,{method:'POST'}); await openInst(id);}catch(e){showError(e.message)}}
async function connect(id,node){try{await api(`instances/${id}/connect`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:node})}); await openInst(id);}catch(e){showError(e.message)}}
async function testNode(id,node){try{await api(`instances/${id}/test_node`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:node})}); await openInst(id);}catch(e){showError(e.message)}}
async function logs(id){try{const data=await api(`instances/${id}/logs`);el('content').innerHTML+=`<div class="card"><h3>Logs</h3><pre>${esc(data.logs.map(x=>`[${x.timestamp}] ${x.level} ${x.module}: ${x.message}`).join('\\n'))}</pre></div>`}catch(e){showError(e.message)}}
async function logout(){await fetch('./api/logout',{method:'POST'});location.reload()}
load().catch(e=>{el('content').innerHTML='<div class="card bad">'+esc(e.message)+'</div>'});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def secret_path(self) -> str:
        return str(load_console_auth().get("secret_path") or "")

    def effective_path(self) -> str:
        request_path = urllib.parse.urlsplit(self.path).path
        secret = self.secret_path().strip("/")
        if request_path == f"/{secret}":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"/{secret}/")
            self.end_headers()
            return ""
        prefix = f"/{secret}/"
        if request_path.startswith(prefix):
            return "/" + request_path[len(prefix):]
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()
        return ""

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[console] {fmt % args}", flush=True)

    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def authorized(self) -> bool:
        cookie = self.headers.get("Cookie", "")
        token = ""
        for item in cookie.split(";"):
            item = item.strip()
            if item.startswith("console_session="):
                token = item.split("=", 1)[1]
                break
        return bool(token and sessions.get(token, 0) > time.time())

    def do_GET(self) -> None:
        path = self.effective_path()
        if not path:
            return
        if not self.authorized():
            if path in ("/", "/index.html"):
                self.send_bytes(LOGIN_HTML.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self.send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if path in ("/", "/index.html"):
            self.send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/instances":
            self.send_json({"instances": [instance_state(inst) for inst in load_instances()]})
        elif path.startswith("/api/instances/"):
            parts = path.strip("/").split("/")
            if len(parts) < 3:
                self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            inst = instance_by_id(parts[2])
            if not inst:
                self.send_json({"error": "unknown instance"}, HTTPStatus.NOT_FOUND)
                return
            action = parts[3] if len(parts) > 3 else "status"
            if action == "status":
                self.send_json(instance_state(inst))
            elif action == "nodes":
                self.send_json(stripped_nodes(inst))
            elif action == "logs":
                self.send_json(read_logs(inst))
            elif action == "gateway_status":
                self.send_json(backend_request(inst, "/api/gateway_status"))
            else:
                self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        else:
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = self.effective_path()
        if not path:
            return
        if path == "/api/login":
            payload = self.body_json()
            auth = load_console_auth()
            if payload.get("username") == auth.get("username") and payload.get("password") == auth.get("password"):
                token = uuid.uuid4().hex
                sessions[token] = time.time() + 30 * 24 * 3600
                body = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Set-Cookie", f"console_session={token}; Path=/{self.secret_path().strip('/')}/; HttpOnly; SameSite=Lax; Max-Age=2592000")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json({"ok": False, "error": "login failed"}, HTTPStatus.FORBIDDEN)
            return
        if path == "/api/logout":
            self.send_response(HTTPStatus.OK)
            self.send_header("Set-Cookie", f"console_session=; Path=/{self.secret_path().strip('/')}/; HttpOnly; SameSite=Lax; Max-Age=0")
            self.end_headers()
            return
        if not self.authorized():
            self.send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if not path.startswith("/api/instances/"):
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        parts = path.strip("/").split("/")
        if len(parts) < 4:
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        inst = instance_by_id(parts[2])
        if not inst:
            self.send_json({"error": "unknown instance"}, HTTPStatus.NOT_FOUND)
            return
        action = parts[3]
        payload = self.body_json()
        if action == "service":
            self.send_json(service_action(inst["service"], str(payload.get("action") or "")))
        elif action in {"connect", "disconnect", "refresh_nodes", "test_proxy", "test_node"}:
            self.send_json(backend_request(inst, f"/api/{action}", method="POST", payload=payload))
        else:
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    auth = load_console_auth()
    host = str(auth.get("host") or CONSOLE_HOST)
    port = int(auth.get("port") or CONSOLE_PORT)
    print(f"AimiliVPN console listening on {host}:{port}/{auth['secret_path']}/", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
