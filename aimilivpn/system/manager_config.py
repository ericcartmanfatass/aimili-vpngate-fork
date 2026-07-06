from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aimilivpn.system.runtime_paths import RuntimePaths, build_runtime_paths


def env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        print(f"[配置警告] 环境变量 {name}={raw!r} 不是有效整数，使用默认值 {default}", flush=True)
        value = default
    if min_value is not None and value < min_value:
        print(f"[配置警告] 环境变量 {name}={value} 小于允许值 {min_value}，使用默认值 {default}", flush=True)
        return default
    if max_value is not None and value > max_value:
        print(f"[配置警告] 环境变量 {name}={value} 大于允许值 {max_value}，使用默认值 {default}", flush=True)
        return default
    return value


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
    invalid_backoff_seconds: int
    instance_id: str
    tun_dev: str
    policy_table: str
    allowed_countries: set[str]
    exclude_datacenter: bool
    allow_insecure_fetch: bool


def load_manager_runtime_config(root_dir: Path) -> ManagerRuntimeConfig:
    resolved_root = root_dir.resolve()
    target_valid_nodes = env_int("TARGET_VALID_NODES", 3, 1)
    allowed_countries = {
        item.strip()
        for item in os.environ.get("ALLOWED_COUNTRIES", "").strip().upper().split(",")
        if item.strip()
    }
    return ManagerRuntimeConfig(
        root_dir=resolved_root,
        paths=build_runtime_paths(resolved_root, os.environ.get("VPNGATE_DATA_DIR")),
        api_url="https://www.vpngate.net/api/iphone/",
        fetch_interval_seconds=env_int("FETCH_INTERVAL_SECONDS", 1260, 1),
        check_interval_seconds=env_int("CHECK_INTERVAL_SECONDS", 1260, 1),
        target_valid_nodes=target_valid_nodes,
        max_scan_rows=env_int("MAX_SCAN_ROWS", 300, 1),
        openvpn_test_timeout_seconds=env_int("OPENVPN_TEST_TIMEOUT_SECONDS", 35, 1),
        openvpn_maintenance_test_timeout_seconds=env_int("OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS", 8, 3),
        node_test_workers=env_int("NODE_TEST_WORKERS", 2, 1, 10),
        max_maintenance_test_nodes=env_int("MAX_MAINTENANCE_TEST_NODES", max(18, target_valid_nodes * 6), 1),
        node_retest_interval_seconds=env_int("NODE_RETEST_INTERVAL_SECONDS", 6 * 3600, 60),
        openvpn_cmd=os.environ.get("OPENVPN_CMD", "openvpn"),
        openvpn_auth_user=os.environ.get("OPENVPN_AUTH_USER", "vpn"),
        openvpn_auth_pass=os.environ.get("OPENVPN_AUTH_PASS", "vpn"),
        local_proxy_host=os.environ.get("LOCAL_PROXY_HOST", "127.0.0.1"),
        local_proxy_port=env_int("LOCAL_PROXY_PORT", 7928, 1, 65535),
        ui_host=os.environ.get("UI_HOST", "::"),
        ui_port=env_int("UI_PORT", 8787, 1, 65535),
        invalid_backoff_seconds=env_int("INVALID_BACKOFF_SECONDS", 30 * 60, 1),
        instance_id=os.environ.get("INSTANCE_ID", "default").strip().lower() or "default",
        tun_dev=os.environ.get("TUN_DEV", "tun0").strip() or "tun0",
        policy_table=os.environ.get("POLICY_TABLE", "100").strip() or "100",
        allowed_countries=allowed_countries,
        exclude_datacenter=os.environ.get("EXCLUDE_DATACENTER", "0").strip().lower() in ("1", "true", "yes", "on"),
        allow_insecure_fetch=os.environ.get("ALLOW_INSECURE_FETCH", "0").strip().lower() in ("1", "true", "yes", "on"),
    )
