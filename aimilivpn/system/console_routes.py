from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from aimilivpn.core.auth import generate_session_token, verify_password, verify_username
from aimilivpn.core.global_config import APP_VERSION
from aimilivpn.system.console_backend import backend_request, service_action, service_active, systemctl
from aimilivpn.system.console_config import (
    CONFIG_DIR,
    INSTALL_DIR,
    INSTANCES_FILE,
    LOGIN_RATE_LIMIT_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    MAX_REQUEST_BODY_BYTES,
    REQUEST_TIMEOUT_SECONDS,
    TRUST_PROXY_HEADERS,
    TRUSTED_PROXY_ADDRESSES,
    load_console_auth,
)
from aimilivpn.system.instance_lifecycle import (
    InstanceLifecycle,
    LifecycleError,
    detect_host_resource_conflicts,
)
from aimilivpn.system.console_instances import (
    instance_by_id,
    instance_state as build_instance_state,
    load_available_country_catalog,
    load_instances,
    read_logs,
    stripped_nodes as build_stripped_nodes,
)
from aimilivpn.system.console_security import LoginAttemptLimiter
from aimilivpn.system.global_console import GlobalConsoleRuntime
from aimilivpn.web.auth_routes import parse_cookie_header, redact_secret_path
from aimilivpn.web.http_utils import HttpResponseMixin, InvalidRequestBody, RequestBodyTooLarge
from aimilivpn.web.proxy_trust import (
    request_client_ip,
    request_uses_trusted_https,
    secure_cookie_suffix,
)
from aimilivpn.web.static_assets import get_static_asset, guess_content_type
from aimilivpn.web.templates import get_console_index_html, get_console_login_html


SESSION_TTL_SECONDS = 30 * 24 * 3600
sessions: dict[str, float] = {}
sessions_lock = threading.RLock()
login_limiter = LoginAttemptLimiter(LOGIN_RATE_LIMIT_ATTEMPTS, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
_auth_fingerprint: str | None = None
instance_lifecycle = InstanceLifecycle(
    config_dir=CONFIG_DIR,
    install_dir=INSTALL_DIR,
    instances_file=INSTANCES_FILE,
    token_file=CONFIG_DIR / "instance_api_token",
    systemctl=systemctl,
    lock=threading.RLock(),
    resource_probe=detect_host_resource_conflicts,
    country_catalog=load_available_country_catalog,
)
_global_console_runtime: GlobalConsoleRuntime | None = None


def global_console_runtime() -> GlobalConsoleRuntime:
    global _global_console_runtime
    if (
        _global_console_runtime is None
        or _global_console_runtime.config_dir != CONFIG_DIR
        or _global_console_runtime.install_dir != INSTALL_DIR
    ):
        _global_console_runtime = GlobalConsoleRuntime.build(CONFIG_DIR, INSTALL_DIR)
    return _global_console_runtime

LOGIN_HTML = """<!doctype html><html><body><h1>AimiliVPN Console Login</h1></body></html>"""
INDEX_HTML = """<!doctype html><html><body><h1>AimiliVPN Console</h1></body></html>"""


def _fingerprint_auth(auth: dict[str, Any]) -> str:
    controlled = {
        key: auth.get(key)
        for key in ("username", "password_hash", "secret_path", "host", "port")
    }
    encoded = json.dumps(controlled, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sync_auth_session_state(auth: dict[str, Any]) -> None:
    global _auth_fingerprint
    fingerprint = _fingerprint_auth(auth)
    with sessions_lock:
        if _auth_fingerprint is not None and _auth_fingerprint != fingerprint:
            sessions.clear()
            print("[console audit] authentication configuration changed; sessions revoked", flush=True)
        _auth_fingerprint = fingerprint


def cleanup_expired_sessions(now: float | None = None) -> None:
    current = time.time() if now is None else now
    with sessions_lock:
        expired = [token for token, expires_at in sessions.items() if expires_at <= current]
        for token in expired:
            sessions.pop(token, None)


def reset_runtime_security_state() -> None:
    global _auth_fingerprint
    with sessions_lock:
        sessions.clear()
        _auth_fingerprint = None
    login_limiter.clear()


def instance_state(inst: dict[str, Any]) -> dict[str, Any]:
    return build_instance_state(inst, service_active=service_active)


def stripped_nodes(inst: dict[str, Any]) -> dict[str, Any]:
    return build_stripped_nodes(inst, state_factory=instance_state)


class Handler(HttpResponseMixin, BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def auth_config(self) -> dict[str, Any]:
        auth = load_console_auth()
        sync_auth_session_state(auth)
        return auth

    def secret_path(self) -> str:
        return str(self.auth_config().get("secret_path") or "")

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
        return self.read_json_body(MAX_REQUEST_BODY_BYTES)

    def safe_error_json(self, data: dict[str, Any], status: HTTPStatus) -> None:
        try:
            self.send_json(data, status)
        except OSError as exc:
            print(f"[console audit] response write failed: {type(exc).__name__}", flush=True)

    def session_token(self) -> str:
        return parse_cookie_header(self.headers.get("Cookie", "")).get("console_session", "")

    def authorized(self) -> bool:
        self.auth_config()
        token = self.session_token()
        cleanup_expired_sessions()
        with sessions_lock:
            return bool(token and sessions.get(token, 0) > time.time())

    def client_ip(self) -> str:
        return request_client_ip(
            self,
            trust_proxy_headers=TRUST_PROXY_HEADERS,
            trusted_proxy_addresses=TRUSTED_PROXY_ADDRESSES,
        )

    def is_secure_request(self) -> bool:
        return request_uses_trusted_https(
            self,
            trust_proxy_headers=TRUST_PROXY_HEADERS,
            trusted_proxy_addresses=TRUSTED_PROXY_ADDRESSES,
        )

    def do_GET(self) -> None:
        try:
            self._handle_get()
        except Exception as exc:
            print(f"[console audit] GET request failed: {type(exc).__name__}", flush=True)
            self.safe_error_json({"error": "服务器内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_get(self) -> None:
        path = self.effective_path()
        if not path:
            return
        if not self.authorized():
            if path in ("/", "/index.html"):
                self.send_bytes(get_console_login_html(LOGIN_HTML).encode("utf-8"), "text/html; charset=utf-8")
            else:
                self.send_json({"error": "未授权"}, HTTPStatus.UNAUTHORIZED)
            return
        if path in ("/", "/index.html"):
            self.send_bytes(get_console_index_html(INDEX_HTML).encode("utf-8"), "text/html; charset=utf-8")
        elif path.startswith("/static/"):
            asset_path = urllib.parse.unquote(path.removeprefix("/static/"))
            try:
                asset = get_static_asset(asset_path)
            except ValueError:
                self.send_json({"error": "静态资源路径无效"}, HTTPStatus.BAD_REQUEST)
                return
            if asset is None:
                self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
                return
            self.send_bytes(asset, guess_content_type(asset_path))
        elif path == "/api/instances":
            self.send_json({"instances": [instance_state(inst) for inst in load_instances()]})
        elif path == "/api/instance-catalog":
            self.send_json({"catalog": instance_lifecycle.catalog()})
        elif path == "/api/global/settings":
            self.send_json({"settings": global_console_runtime().settings()})
        elif path in {"/api/global/tasks", "/api/global/status"}:
            self.send_json({"task": global_console_runtime().task_status()})
        elif path == "/api/global/nodes":
            self.send_json(global_console_runtime().nodes())
        elif path == "/api/global/logs":
            self.send_json(global_console_runtime().logs_security())
        elif path == "/api/global/backup":
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            backup_type = str((query.get("type") or ["config"])[0] or "config")
            payload = global_console_runtime().backup_payload(backup_type)
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="aimilivpn-v{APP_VERSION}-{backup_type}.json"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/api/instances/"):
            parts = path.strip("/").split("/")
            if len(parts) < 3:
                self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
                return
            inst = instance_by_id(parts[2])
            if not inst:
                self.send_json({"error": "未找到实例"}, HTTPStatus.NOT_FOUND)
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
                self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
        else:
            self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            self._handle_post()
        except RequestBodyTooLarge:
            self.safe_error_json({"error": "请求内容过大"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except (InvalidRequestBody, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            self.safe_error_json({"error": "请求内容无效"}, HTTPStatus.BAD_REQUEST)
        except (socket.timeout, TimeoutError):
            self.safe_error_json({"error": "请求超时"}, HTTPStatus.REQUEST_TIMEOUT)
        except Exception as exc:
            print(f"[console audit] POST request failed: {type(exc).__name__}", flush=True)
            self.safe_error_json({"error": "服务器内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_post(self) -> None:
        path = self.effective_path()
        if not path:
            return
        if path == "/api/login":
            client_ip = self.client_ip()
            if not login_limiter.allow(client_ip):
                print("[console audit] login rate limit exceeded", flush=True)
                self.send_json({"ok": False, "error": "登录失败"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            payload = self.body_json()
            try:
                auth = self.auth_config()
                valid = verify_username(
                    str(payload.get("username") or ""), str(auth.get("username") or "")
                ) and verify_password(
                    str(payload.get("password") or ""), str(auth.get("password_hash") or "")
                )
            except Exception as exc:
                print(f"[console audit] login verification failed: {type(exc).__name__}", flush=True)
                valid = False
            if valid:
                login_limiter.reset(client_ip)
                token = generate_session_token()
                with sessions_lock:
                    sessions[token] = time.time() + SESSION_TTL_SECONDS
                body = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Set-Cookie",
                    f"console_session={token}; Path=/{self.secret_path().strip('/')}/; "
                    f"HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}{secure_cookie_suffix(self)}",
                )
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json({"ok": False, "error": "登录失败"}, HTTPStatus.FORBIDDEN)
            return
        if path == "/api/logout":
            token = self.session_token()
            if token:
                with sessions_lock:
                    sessions.pop(token, None)
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Set-Cookie",
                f"console_session=; Path=/{self.secret_path().strip('/')}/; "
                f"HttpOnly; SameSite=Lax; Max-Age=0{secure_cookie_suffix(self)}",
            )
            self.end_headers()
            return
        if not self.authorized():
            self.send_json({"error": "未授权"}, HTTPStatus.UNAUTHORIZED)
            return
        print(f"[console audit] mutation path={path} client={self.client_ip()}", flush=True)
        if path == "/api/global/settings":
            payload = self.body_json()
            self.send_json({"ok": True, "settings": global_console_runtime().save_settings(payload)})
            return
        if path == "/api/global/refresh":
            self.send_json(global_console_runtime().refresh())
            return
        if path == "/api/global/scamalytics/test":
            result = global_console_runtime().test_scamalytics()
            self.send_json(result, HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_GATEWAY)
            return
        if path == "/api/global/backup/preview":
            payload = self.body_json()
            candidate = payload.get("backup", payload)
            if not isinstance(candidate, dict):
                raise ValueError("backup must be an object")
            self.send_json({"ok": True, "preview": global_console_runtime().preview_restore(candidate)})
            return
        if path == "/api/global/backup/restore":
            payload = self.body_json()
            candidate = payload.get("backup")
            if not isinstance(candidate, dict):
                raise ValueError("backup must be an object")
            result = global_console_runtime().restore(
                candidate,
                confirmed=bool(payload.get("confirmed", False)),
            )
            self.send_json(result)
            return
        if path in {"/api/instances", "/api/instances/validate"}:
            payload = self.body_json()
            try:
                if path.endswith("/validate"):
                    selected = instance_lifecycle.validate_create(
                        str(payload.get("country") or ""),
                        str(payload.get("id") or ""),
                    )
                    self.send_json({"ok": True, "instance": selected})
                else:
                    created = instance_lifecycle.create(
                        str(payload.get("country") or ""),
                        str(payload.get("id") or ""),
                    )
                    self.send_json({"ok": True, "instance": created}, HTTPStatus.CREATED)
            except LifecycleError as exc:
                self.send_json(
                    {"ok": False, "error": exc.message, "error_code": exc.code},
                    HTTPStatus(exc.status),
                )
            return
        if not path.startswith("/api/instances/"):
            self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
            return
        parts = path.strip("/").split("/")
        if len(parts) < 4:
            self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
            return
        inst = instance_by_id(parts[2])
        if not inst:
            self.send_json({"error": "未找到实例"}, HTTPStatus.NOT_FOUND)
            return
        action = parts[3]
        payload = self.body_json()
        if action == "service":
            self.send_json(
                service_action(inst["service"], str(payload.get("action") or ""), instance_id=inst["id"])
            )
        elif action in {"connect", "disconnect", "refresh_nodes", "test_proxy", "test_node"}:
            self.send_json(backend_request(inst, f"/api/{action}", method="POST", payload=payload))
        else:
            self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        try:
            self._handle_delete()
        except RequestBodyTooLarge:
            self.safe_error_json({"error": "请求内容过大"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except (InvalidRequestBody, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            self.safe_error_json({"error": "请求内容无效"}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            print(f"[console audit] DELETE request failed: {type(exc).__name__}", flush=True)
            self.safe_error_json({"error": "服务器内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_delete(self) -> None:
        path = self.effective_path()
        if not path:
            return
        if not self.authorized():
            self.send_json({"error": "未授权"}, HTTPStatus.UNAUTHORIZED)
            return
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "instances"]:
            self.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
            return
        payload = self.body_json()
        instance_id = parts[2]
        retain_data = payload.get("retain_data", True)
        if not isinstance(retain_data, bool):
            raise InvalidRequestBody("retain_data must be boolean")
        print(f"[console audit] mutation path=/api/instances/<id> client={self.client_ip()}", flush=True)
        try:
            result = instance_lifecycle.delete(
                instance_id,
                confirmation=str(payload.get("confirmation") or ""),
                retain_data=retain_data,
                purge_data_confirmation=str(payload.get("purge_data_confirmation") or ""),
            )
        except LifecycleError as exc:
            self.send_json(
                {"ok": False, "error": exc.message, "error_code": exc.code},
                HTTPStatus(exc.status),
            )
            return
        self.send_json({"ok": True, **result})
