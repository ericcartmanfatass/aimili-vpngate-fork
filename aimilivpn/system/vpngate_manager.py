#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from typing import Any

from aimilivpn.system import manager_runtime_context as runtime_context
from aimilivpn.system.manager_compat_callbacks import bind_compat_callbacks
from aimilivpn.system.manager_compat_exports import export_context_globals


MANAGER_CONTEXT = runtime_context.build_manager_runtime_context(compiled=bool(globals().get("__compiled__")))

export_context_globals(globals(), MANAGER_CONTEXT, runtime_context)

def enrich_quality_with_scamalytics(result: QualityResult) -> QualityResult:
    return manager_quality_runtime.enrich_quality_with_scamalytics(
        result,
        provider_getter=get_scamalytics_provider,
    )


def record_quality_result_from_probe(
    node: dict[str, Any],
    openvpn_success: bool | None,
    latency_ms: int,
    probe_message: str = "",
) -> QualityResult:
    return manager_quality_runtime.record_quality_result_from_probe(
        node,
        openvpn_success,
        latency_ms,
        probe_message,
        provider_getter=get_scamalytics_provider,
    )


def check_quality_ip(ip: str) -> QualityResult:
    return manager_quality_runtime.check_quality_ip(
        ip,
        provider_getter=get_scamalytics_provider,
    )


def check_quality_region(region_id: str, limit: int = 20) -> dict[str, Any]:
    return manager_quality_runtime.check_quality_region(region_id, limit)


def openvpn_command(config_file: str, route_nopull: bool, dev: str = TUN_DEV) -> list[str]:
    return MANAGER_CONTEXT.openvpn_command(config_file, route_nopull, dev)


def update_handshake_status(line_lower: str) -> None:
    MANAGER_CONTEXT.update_handshake_status(line_lower)


def run_openvpn_until_ready(
    config_file: str,
    keep_alive: bool,
    route_nopull: bool,
    timeout: int | None = None,
    dev: str = TUN_DEV,
) -> tuple[bool, str, subprocess.Popen[str] | None]:
    return MANAGER_CONTEXT.run_openvpn_until_ready(
        config_file,
        keep_alive=keep_alive,
        route_nopull=route_nopull,
        timeout=timeout,
        dev=dev,
    )


def test_multiple_nodes(
    node_ids: list[str],
    timeout: int = OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS,
    max_workers: int = NODE_TEST_WORKERS,
) -> list[dict[str, Any]]:
    return MANAGER_CONTEXT.test_multiple_nodes(
        node_ids,
        timeout=timeout,
        max_workers=max_workers,
    )


def auto_switch_node(attempt: int = 0) -> None:
    MANAGER_CONTEXT.auto_switch_node(attempt)


def connect_node(node_id: str) -> str:
    return MANAGER_CONTEXT.connect_node(node_id)


def maintain_valid_nodes(force: bool = False) -> str:
    return MANAGER_CONTEXT.maintain_valid_nodes(force)



bind_compat_callbacks(globals())

Handler = manager_entry_runtime.handler_class()
MANAGER_CONTEXT.handler_class = Handler


def main() -> None:
    MANAGER_CONTEXT.main()


if __name__ == "__main__":
    main()
