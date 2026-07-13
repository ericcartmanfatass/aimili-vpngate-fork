from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from aimilivpn.web.route_contexts import AuthRouteContext
from aimilivpn.web.api_errors import send_api_error
from aimilivpn.web.proxy_trust import secure_cookie_suffix


@dataclass(frozen=True)
class AccessPathResult:
    effective_path: str = ""
    status: HTTPStatus | None = None
    redirect_location: str | None = None


def parse_cookie_header(cookie_header: str | None) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if not cookie_header:
        return cookies
    for item in cookie_header.split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            cookies[key] = value.strip()
    return cookies


def redact_secret_path(message: str, secret_path: str | None) -> str:
    secret = str(secret_path or "").strip("/")
    if not secret:
        return message
    return message.replace(f"/{secret}", "/<secret-path>")


def is_session_authorized(
    cookie_header: str | None,
    sessions: Mapping[str, float],
    now: float,
    *,
    trusted: bool = False,
) -> bool:
    if trusted:
        return True
    if isinstance(sessions, MutableMapping):
        for token, expires_at in list(sessions.items()):
            if expires_at <= now:
                sessions.pop(token, None)
    session_token = parse_cookie_header(cookie_header).get("session")
    if not session_token:
        return False
    expires_at = sessions.get(session_token)
    return expires_at is not None and expires_at > now


def resolve_secret_path_request(
    request_path: str,
    secret_path: str | None,
    *,
    trusted: bool = False,
) -> AccessPathResult:
    if trusted:
        return AccessPathResult(effective_path=request_path)

    secret = str(secret_path or "").strip("/")
    if not secret:
        return AccessPathResult(effective_path=request_path)

    secret_root = f"/{secret}"
    if request_path == secret_root:
        return AccessPathResult(status=HTTPStatus.FOUND, redirect_location=f"{secret_root}/")

    prefix = f"{secret_root}/"
    if request_path.startswith(prefix):
        return AccessPathResult(effective_path="/" + request_path[len(prefix):])

    return AccessPathResult(status=HTTPStatus.NOT_FOUND)


def _send_cookie_json(handler: Any, payload: dict[str, Any], cookie: str, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Set-Cookie", cookie)
    handler.end_headers()
    handler.wfile.write(body)

def handle_auth_post(handler: Any, effective_path: str, context: AuthRouteContext) -> bool:
    if effective_path == "/api/login":
        try:
            payload = handler.read_json_body()
            input_pwd = str(payload.get("password") or "")
            input_uname = str(payload.get("username") or "")

            ui_cfg = context.load_ui_config()
            expected_pwd = ui_cfg.get("password_hash", "")
            expected_uname = ui_cfg.get("username", "admin")

            if expected_pwd and context.verify_password(input_pwd, expected_pwd) and context.verify_username(input_uname, expected_uname):
                token = context.generate_session_token()
                context.add_session(token, context.now() + 30 * 24 * 3600)
                secret_path = context.get_secret_path()
                cookie_path = f"/{secret_path}/" if secret_path else "/"
                _send_cookie_json(
                    handler,
                    {"ok": True},
                    f"session={token}; Path={cookie_path}; HttpOnly; SameSite=Lax; Max-Age=2592000"
                    f"{secure_cookie_suffix(handler)}",
                )
            else:
                handler.send_json({"ok": False, "error": "用户名或密码不正确，请重新输入"}, HTTPStatus.FORBIDDEN)
        except Exception as exc:
            send_api_error(handler, "authentication_failed", exc=exc, operation="login")
        return True

    if effective_path == "/api/logout":
        try:
            cookies = parse_cookie_header(handler.headers.get("Cookie", ""))
            session_token = cookies.get("session")
            if session_token:
                context.remove_session(session_token)

            secret_path = context.get_secret_path()
            cookie_path = f"/{secret_path}/" if secret_path else "/"
            _send_cookie_json(
                handler,
                {"ok": True},
                f"session=; Path={cookie_path}; HttpOnly; SameSite=Lax; Max-Age=0; "
                f"Expires=Thu, 01 Jan 1970 00:00:00 GMT{secure_cookie_suffix(handler)}",
            )
        except Exception as exc:
            send_api_error(handler, "logout_failed", exc=exc, operation="logout")
        return True

    return False
