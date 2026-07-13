from __future__ import annotations

from typing import Any

from aimilivpn.system.manager_config import build_manager_runtime_environment

CONFIG_ATTRIBUTES = (
    "api_url",
    "fetch_interval_seconds",
    "check_interval_seconds",
    "target_valid_nodes",
    "max_scan_rows",
    "openvpn_test_timeout_seconds",
    "openvpn_maintenance_test_timeout_seconds",
    "node_test_workers",
    "max_maintenance_test_nodes",
    "node_retest_interval_seconds",
    "openvpn_cmd",
    "openvpn_auth_user",
    "openvpn_auth_pass",
    "local_proxy_host",
    "local_proxy_port",
    "ui_host",
    "ui_port",
    "trust_proxy_headers",
    "trusted_proxy_addresses",
    "invalid_backoff_seconds",
    "instance_id",
    "tun_dev",
    "policy_table",
    "allowed_countries",
    "exclude_datacenter",
    "allow_insecure_fetch",
    "storage_backend",
    "sqlite_db_path",
)

PATH_ATTRIBUTES = (
    "data_dir",
    "config_dir",
    "nodes_file",
    "state_file",
    "auth_file",
    ("upstream_proxy_auth_file_path", "upstream_proxy_auth_file"),
    "blacklist_file",
    "regions_file",
    "quality_results_file",
    "settings_file",
)


def apply_runtime_environment(ctx: Any, *, compiled: bool = False) -> None:
    ctx.environment = build_manager_runtime_environment(compiled=compiled)
    ctx.root_dir = ctx.environment.root_dir
    ctx.config = ctx.environment.config
    for name in CONFIG_ATTRIBUTES:
        setattr(ctx, name, getattr(ctx.config, name))

    ctx.runtime_paths = ctx.environment.paths
    for item in PATH_ATTRIBUTES:
        target, source = item if isinstance(item, tuple) else (item, item)
        setattr(ctx, target, getattr(ctx.runtime_paths, source))
