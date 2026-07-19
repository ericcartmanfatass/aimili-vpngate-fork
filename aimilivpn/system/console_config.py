from __future__ import annotations

import json
import os
import secrets
import string
from pathlib import Path
from typing import Any

from aimilivpn.core.auth import generate_password, migrate_auth_config
from aimilivpn.web.proxy_trust import parse_trusted_proxy_addresses


def env_text(name: str, default: str) -> str:
    value = (os.environ.get(name) or "").strip()
    return value or default


def env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.environ.get(name)
    raw_text = raw.strip() if raw is not None else ""
    try:
        value = int(raw_text) if raw_text else default
    except (TypeError, ValueError):
        return default
    if min_value is not None and value < min_value:
        return default
    if max_value is not None and value > max_value:
        return default
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


CONFIG_DIR = Path(env_text("AIMILIVPN_CONFIG_DIR", "/etc/aimilivpn"))
INSTALL_DIR = Path(env_text("AIMILIVPN_INSTALL_DIR", "/opt/aimilivpn"))
AUTH_FILE = Path(env_text("AIMILIVPN_CONSOLE_AUTH", str(CONFIG_DIR / "console_auth.json")))
INITIAL_PASSWORD_FILE = Path(
    env_text(
        "AIMILIVPN_CONSOLE_INITIAL_PASSWORD_FILE",
        str(CONFIG_DIR / "console_initial_password"),
    )
)
INSTANCES_FILE = Path(env_text("AIMILIVPN_INSTANCES_FILE", str(CONFIG_DIR / "instances.json")))
CONSOLE_HOST = env_text("CONSOLE_HOST", "127.0.0.1")
CONSOLE_PORT = env_int("CONSOLE_PORT", 8788, 1, 65535)
MAX_REQUEST_BODY_BYTES = env_int("CONSOLE_MAX_REQUEST_BODY_BYTES", 1048576, 1024, 1048576)
REQUEST_TIMEOUT_SECONDS = env_int("CONSOLE_REQUEST_TIMEOUT_SECONDS", 10, 1, 120)
MAX_REQUEST_THREADS = env_int("CONSOLE_MAX_REQUEST_THREADS", 32, 4, 256)
LOGIN_RATE_LIMIT_ATTEMPTS = env_int("CONSOLE_LOGIN_RATE_LIMIT_ATTEMPTS", 5, 1, 100)
LOGIN_RATE_LIMIT_WINDOW_SECONDS = env_int("CONSOLE_LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60, 1, 3600)
TRUST_PROXY_HEADERS = env_bool("AIMILIVPN_TRUST_PROXY_HEADERS")
TRUSTED_PROXY_ADDRESSES = parse_trusted_proxy_addresses(
    os.environ.get("AIMILIVPN_TRUSTED_PROXY_ADDRESSES")
)


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


def write_initial_credentials(path: Path, username: str, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        f"用户名: {username}\n一次性密码: {password}\n"
        "请登录后立即修改密码，并删除此文件。\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)
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
    cfg, auth_changed, generated_password = migrate_auth_config(
        cfg,
        password_factory=lambda: generate_password(24),
    )
    changed = changed or auth_changed
    if generated_password:
        write_initial_credentials(INITIAL_PASSWORD_FILE, str(cfg.get("username") or "admin"), generated_password)
    if changed or not AUTH_FILE.exists():
        write_json(AUTH_FILE, cfg)
    if generated_password:
        print(f"[Console] 首次登录凭据已写入受限文件: {INITIAL_PASSWORD_FILE}", flush=True)
    return cfg
