from __future__ import annotations

import json
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from aimilivpn.core.auth import generate_session_token, verify_password, verify_username
from aimilivpn.system.console_backend import backend_request, service_action, service_active
from aimilivpn.system.console_config import (
    TRUST_PROXY_HEADERS,
    TRUSTED_PROXY_ADDRESSES,
    load_console_auth,
)
from aimilivpn.system.console_instances import (
    instance_by_id,
    instance_state as build_instance_state,
    load_instances,
    read_logs,
    stripped_nodes as build_stripped_nodes,
)
from aimilivpn.web.http_utils import HttpResponseMixin
from aimilivpn.web.auth_routes import redact_secret_path
from aimilivpn.web.proxy_trust import request_uses_trusted_https, secure_cookie_suffix
from aimilivpn.web.static_assets import get_static_asset, guess_content_type
from aimilivpn.web.templates import get_console_index_html, get_console_login_html


sessions: dict[str, float] = {}

LOGIN_HTML = """<!doctype html><html><body><h1>AimiliVPN Console Login</h1></body></html>"""
INDEX_HTML = """<!doctype html><html><body><h1>AimiliVPN Console</h1></body></html>"""


def instance_state(inst: dict[str, Any]) -> dict[str, Any]:
    return build_instance_state(inst, service_active=service_active)


def stripped_nodes(inst: dict[str, Any]) -> dict[str, Any]:
    return build_stripped_nodes(inst, state_factory=instance_state)


class Handler(HttpResponseMixin, BaseHTTPRequestHandler):
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
        message = redact_secret_path(fmt % args, self.secret_path())
        print(f"[console] {message}", flush=True)

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

    def is_secure_request(self) -> bool:
        return request_uses_trusted_https(
            self,
            trust_proxy_headers=TRUST_PROXY_HEADERS,
            trusted_proxy_addresses=TRUSTED_PROXY_ADDRESSES,
        )

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
                self.send_header(
                    "Set-Cookie",
                    f"console_session={token}; Path=/{self.secret_path().strip('/')}/; "
                    f"HttpOnly; SameSite=Lax; Max-Age=2592000{secure_cookie_suffix(self)}",
                )
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json({"ok": False, "error": "login failed"}, HTTPStatus.FORBIDDEN)
            return
        if path == "/api/logout":
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Set-Cookie",
                f"console_session=; Path=/{self.secret_path().strip('/')}/; "
                f"HttpOnly; SameSite=Lax; Max-Age=0{secure_cookie_suffix(self)}",
            )
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
