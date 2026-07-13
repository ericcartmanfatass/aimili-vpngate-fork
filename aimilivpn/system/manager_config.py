from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aimilivpn.core.config import AppConfig, env_bool, env_int, env_text, load_config
from aimilivpn.system.runtime_paths import RuntimePaths, build_runtime_paths


def bounded_int(value: Any, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


def env_choice(name: str, default: str, allowed: set[str]) -> str:
    raw = os.environ.get(name)
    raw_text = (raw or "").strip()
    if not raw_text:
        return default
    value = raw_text.lower()
    if value in allowed:
        return value
    print(f"[配置警告] 环境变量 {name}={raw!r} 不是支持的值，使用默认值 {default}", flush=True)
    return default


def resolve_manager_root_dir(
    *,
    compiled: bool = False,
    install_dir: str | Path | None = None,
    cwd: str | Path | None = None,
    executable: str | Path | None = None,
) -> Path:
    if compiled:
        return Path(executable or sys.executable).resolve().parent
    explicit_install_dir = install_dir.strip() if isinstance(install_dir, str) else install_dir
    env_install_dir = (os.environ.get("AIMILIVPN_INSTALL_DIR") or "").strip()
    return Path(explicit_install_dir or env_install_dir or cwd or Path.cwd()).resolve()


def apply_ui_config_overrides(
    ui_config: dict[str, Any],
    ui_host: str,
    ui_port: int,
    local_proxy_port: int,
) -> tuple[str, int, int]:
    if "proxy_port" in ui_config:
        local_proxy_port = bounded_int(ui_config["proxy_port"], local_proxy_port, 1024, 65535)
    if "port" in ui_config:
        ui_port = bounded_int(ui_config["port"], ui_port, 1, 65535)
    if "host" in ui_config:
        ui_host = ui_config["host"]
    return ui_host, ui_port, local_proxy_port


@dataclass(frozen=True)
class ManagerRuntimeConfig:
    root_dir: Path
    paths: RuntimePaths
    app_config: AppConfig
    api_url: str
    fetch_interval_seconds: int
    check_interval_seconds: int
    target_valid_nodes: int
    max_scan_rows: int
    openvpn_test_timeout_seconds: int
    openvpn_maintenance_test_timeout_seconds: int
    node_test_workers: int
    max_maintenance_test_nodes: int
    node_retest_interval_seconds: int
    openvpn_cmd: str
    openvpn_auth_user: str
    openvpn_auth_pass: str
    local_proxy_host: str
    local_proxy_port: int
    ui_host: str
    ui_port: int
    trust_proxy_headers: bool
    trusted_proxy_addresses: tuple[str, ...]
    invalid_backoff_seconds: int
    instance_id: str
    tun_dev: str
    policy_table: str
    allowed_countries: set[str]
    exclude_datacenter: bool
    allow_insecure_fetch: bool
    storage_backend: str
    sqlite_db_path: Path


@dataclass(frozen=True)
class ManagerRuntimeEnvironment:
    root_dir: Path
    config: ManagerRuntimeConfig

    @property
    def paths(self) -> RuntimePaths:
        return self.config.paths


def build_manager_runtime_environment(
    *,
    compiled: bool = False,
    install_dir: str | Path | None = None,
    cwd: str | Path | None = None,
    executable: str | Path | None = None,
) -> ManagerRuntimeEnvironment:
    root_dir = resolve_manager_root_dir(
        compiled=compiled,
        install_dir=install_dir,
        cwd=cwd,
        executable=executable,
    )
    return ManagerRuntimeEnvironment(
        root_dir=root_dir,
        config=load_manager_runtime_config(root_dir),
    )


def load_manager_runtime_config(root_dir: Path) -> ManagerRuntimeConfig:
    resolved_root = root_dir.resolve()
    app_config = load_config(resolved_root)
    runtime_paths = build_runtime_paths(resolved_root, str(app_config.data_dir))
    target_valid_nodes = env_int("TARGET_VALID_NODES", 3, 1)
    sqlite_env = (os.environ.get("SQLITE_DB_PATH") or "").strip()
    sqlite_db_path = Path(sqlite_env).expanduser() if sqlite_env else runtime_paths.data_dir / "aimilivpn.db"
    sqlite_db_path = sqlite_db_path if sqlite_db_path.is_absolute() else resolved_root / sqlite_db_path
    return ManagerRuntimeConfig(
        root_dir=resolved_root,
        paths=runtime_paths,
        app_config=app_config,
        api_url=app_config.api_url,
        fetch_interval_seconds=env_int("FETCH_INTERVAL_SECONDS", 1260, 1),
        check_interval_seconds=env_int("CHECK_INTERVAL_SECONDS", 1260, 1),
        target_valid_nodes=target_valid_nodes,
        max_scan_rows=app_config.max_scan_rows,
        openvpn_test_timeout_seconds=env_int("OPENVPN_TEST_TIMEOUT_SECONDS", 35, 1),
        openvpn_maintenance_test_timeout_seconds=env_int("OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS", 8, 3),
        node_test_workers=env_int("NODE_TEST_WORKERS", 2, 1, 10),
        max_maintenance_test_nodes=env_int("MAX_MAINTENANCE_TEST_NODES", max(18, target_valid_nodes * 6), 1),
        node_retest_interval_seconds=env_int("NODE_RETEST_INTERVAL_SECONDS", 6 * 3600, 60),
        openvpn_cmd=app_config.openvpn_cmd,
        openvpn_auth_user=os.environ.get("OPENVPN_AUTH_USER", "vpn"),
        openvpn_auth_pass=os.environ.get("OPENVPN_AUTH_PASS", "vpn"),
        local_proxy_host=app_config.local_proxy_host,
        local_proxy_port=app_config.local_proxy_port,
        ui_host=app_config.ui_host,
        ui_port=app_config.ui_port,
        trust_proxy_headers=app_config.trust_proxy_headers,
        trusted_proxy_addresses=app_config.trusted_proxy_addresses,
        invalid_backoff_seconds=env_int("INVALID_BACKOFF_SECONDS", 30 * 60, 1),
        instance_id=env_text("INSTANCE_ID", "default").lower(),
        tun_dev=app_config.tun_dev,
        policy_table=app_config.policy_table,
        allowed_countries=app_config.allowed_countries,
        exclude_datacenter=env_bool("EXCLUDE_DATACENTER"),
        allow_insecure_fetch=app_config.allow_insecure_fetch,
        storage_backend=env_choice("STORAGE_BACKEND", "json", {"json", "sqlite"}),
        sqlite_db_path=sqlite_db_path.resolve(),
    )
