#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import secrets
import string
import subprocess
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from aimilivpn.core.auth import generate_password, generate_session_token, migrate_auth_config, verify_password, verify_username
from aimilivpn.web.static_assets import get_static_asset, guess_content_type
from aimilivpn.web.templates import get_console_index_html, get_console_login_html

CONFIG_DIR = Path(os.environ.get("AIMILIVPN_CONFIG_DIR", "/etc/aimilivpn"))
INSTALL_DIR = Path(os.environ.get("AIMILIVPN_INSTALL_DIR", "/opt/aimilivpn"))
AUTH_FILE = Path(os.environ.get("AIMILIVPN_CONSOLE_AUTH", str(CONFIG_DIR / "console_auth.json")))
INSTANCES_FILE = Path(os.environ.get("AIMILIVPN_INSTANCES_FILE", str(CONFIG_DIR / "instances.json")))
CONSOLE_HOST = os.environ.get("CONSOLE_HOST", "0.0.0.0")
CONSOLE_PORT = int(os.environ.get("CONSOLE_PORT", "8788"))

sessions: dict[str, float] = {}


def random_token(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_console_auth() -> dict[str, Any]:
    cfg = {
        "username": "admin",
        "password_hash": "",
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
    if not cfg.get("secret_path"):
        cfg["secret_path"] = "console" + random_token(8)
        changed = True
    cfg, auth_changed, generated_password = migrate_auth_config(cfg, password_factory=lambda: generate_password(24))
    changed = changed or auth_changed
    if generated_password:
        print(f"[console] Generated one-time console password: {generated_password}", flush=True)
    if changed or not AUTH_FILE.exists():
        write_json(AUTH_FILE, cfg)
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


LOGIN_HTML = """<!doctype html><html><body><h1>AimiliVPN Console Login</h1></body></html>"""


INDEX_HTML = """<!doctype html><html><body><h1>AimiliVPN Console</h1></body></html>"""


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
                self.send_bytes(get_console_login_html(LOGIN_HTML).encode("utf-8"), "text/html; charset=utf-8")
            else:
                self.send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if path in ("/", "/index.html"):
            self.send_bytes(get_console_index_html(INDEX_HTML).encode("utf-8"), "text/html; charset=utf-8")
        elif path.startswith("/static/"):
            asset_path = urllib.parse.unquote(path.removeprefix("/static/"))
            try:
                asset = get_static_asset(asset_path)
            except ValueError:
                self.send_json({"error": "invalid static path"}, HTTPStatus.BAD_REQUEST)
                return
            if asset is None:
                self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_bytes(asset, guess_content_type(asset_path))
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
            if verify_username(str(payload.get("username") or ""), str(auth.get("username") or "")) and verify_password(str(payload.get("password") or ""), str(auth.get("password_hash") or "")):
                token = generate_session_token()
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
