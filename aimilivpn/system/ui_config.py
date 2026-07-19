from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.auth import migrate_auth_config
from aimilivpn.system.state_store import read_json_file, write_json_file


EXTRA_UI_CONFIG_KEYS = [
    "host",
    "port",
    "proxy_port",
    "routing_mode",
    "force_country",
    "routing_ip_type",
    "connection_enabled",
    "fixed_node_id",
    "favorite_node_ids",
    "fav_fail_fallback",
]


def generate_username(length: int = 12) -> str:
    if length < 4:
        raise ValueError("username length must be at least 4")
    chars = string.ascii_letters + string.digits
    while True:
        username = "".join(secrets.choice(chars) for _ in range(length))
        if (
            username[0].isalpha()
            and any(ch.islower() for ch in username)
            and any(ch.isupper() for ch in username)
            and any(ch.isdigit() for ch in username)
        ):
            return username


@dataclass(frozen=True)
class UiConfigStore:
    data_dir: Path
    lock: Any
    ui_host: str
    ui_port: int
    proxy_port: int
    bounded_int: Callable[[Any, int, int, int], int]
    password_factory: Callable[[], str]
    username_factory: Callable[[], str] = generate_username

    @property
    def auth_file(self) -> Path:
        return self.data_dir / "ui_auth.json"

    @property
    def initial_password_file(self) -> Path:
        return self.data_dir / "ui_initial_password"

    def default_config(self) -> dict[str, Any]:
        return {
            "username": "",
            "secret_path": "EJsW2EeBo9lY",
            "password_hash": "",
            "host": self.ui_host,
            "port": self.ui_port,
            "proxy_port": self.proxy_port,
            "routing_mode": "auto",
            "force_country": "",
            "routing_ip_type": "all",
            "connection_enabled": True,
            "fixed_node_id": "",
            "favorite_node_ids": [],
            "fav_fail_fallback": True,
        }

    def load(self) -> dict[str, Any]:
        with self.lock:
            config = self.default_config()
            updated = False
            if self.auth_file.exists():
                data = read_json_file(self.auth_file, {}, self.lock)
                if isinstance(data, dict):
                    config.update(data)
                    updated = any(key not in data for key in EXTRA_UI_CONFIG_KEYS)

            if not config.get("username"):
                config["username"] = self.username_factory()
                updated = True

            config, auth_changed, generated_password = migrate_auth_config(
                config,
                password_factory=self.password_factory,
            )
            updated = updated or auth_changed
            if generated_password:
                self._write_initial_credentials(str(config.get("username") or "admin"), generated_password)

            updated = self._normalize_ports(config) or updated

            if not self.auth_file.exists() or updated:
                try:
                    write_json_file(self.auth_file, config, self.lock)
                except Exception:
                    pass
            if generated_password:
                print(f"[认证] 首次登录凭据已写入受限文件: {self.initial_password_file}", flush=True)
            return config

    def save(self, config: dict[str, Any]) -> None:
        migrated, _, _ = migrate_auth_config(config, password_factory=self.password_factory)
        write_json_file(self.auth_file, migrated, self.lock)
        self.initial_password_file.unlink(missing_ok=True)

    def _write_initial_credentials(self, username: str, password: str) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.initial_password_file.with_name(
            f".{self.initial_password_file.name}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            f"用户名: {username}\n一次性密码: {password}\n"
            "请登录后立即修改密码，并删除此文件。\n",
            encoding="utf-8",
        )
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, self.initial_password_file)
        try:
            self.initial_password_file.chmod(0o600)
        except OSError:
            pass

    def _normalize_ports(self, config: dict[str, Any]) -> bool:
        updated = False
        normalized_port = self.bounded_int(config.get("port"), self.ui_port, 1, 65535)
        if normalized_port != config.get("port"):
            config["port"] = normalized_port
            updated = True

        normalized_proxy_port = self.bounded_int(config.get("proxy_port"), self.proxy_port, 1024, 65535)
        if normalized_proxy_port == normalized_port:
            fallback_proxy_port = self.proxy_port if self.proxy_port != normalized_port else 7928
            if fallback_proxy_port == normalized_port:
                fallback_proxy_port = 7929
            normalized_proxy_port = fallback_proxy_port
        if normalized_proxy_port != config.get("proxy_port"):
            config["proxy_port"] = normalized_proxy_port
            updated = True
        return updated
