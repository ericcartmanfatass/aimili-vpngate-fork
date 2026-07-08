from __future__ import annotations

import json
import os
import secrets
import string
from pathlib import Path
from typing import Any

from aimilivpn.core.auth import generate_password, migrate_auth_config


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


CONFIG_DIR = Path(env_text("AIMILIVPN_CONFIG_DIR", "/etc/aimilivpn"))
INSTALL_DIR = Path(env_text("AIMILIVPN_INSTALL_DIR", "/opt/aimilivpn"))
AUTH_FILE = Path(env_text("AIMILIVPN_CONSOLE_AUTH", str(CONFIG_DIR / "console_auth.json")))
INSTANCES_FILE = Path(env_text("AIMILIVPN_INSTANCES_FILE", str(CONFIG_DIR / "instances.json")))
CONSOLE_HOST = env_text("CONSOLE_HOST", "0.0.0.0")
CONSOLE_PORT = env_int("CONSOLE_PORT", 8788, 1, 65535)


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
    cfg, auth_changed, generated_password = migrate_auth_config(
        cfg,
        password_factory=lambda: generate_password(24),
    )
    changed = changed or auth_changed
    if generated_password:
        print(f"[console] Generated one-time console password: {generated_password}", flush=True)
    if changed or not AUTH_FILE.exists():
        write_json(AUTH_FILE, cfg)
    return cfg
