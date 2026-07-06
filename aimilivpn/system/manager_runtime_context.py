from __future__ import annotations

import subprocess
import time
from typing import Any

from aimilivpn.system.socket_resolution import install_ipv4_preferred_getaddrinfo

install_ipv4_preferred_getaddrinfo()
import vpn_utils
from aimilivpn.core.logging_utils import redact_log_message
from aimilivpn.core.models import QualityResult
from aimilivpn.providers.scamalytics import ScamalyticsError
from aimilivpn.system import manager_runtime_context_connection as context_connection
from aimilivpn.system import manager_runtime_context_foundation as context_foundation
from aimilivpn.system import manager_runtime_context_process as context_process
from aimilivpn.system import manager_runtime_context_support as context_support
from aimilivpn.system import manager_runtime_context_web as context_web
from aimilivpn.system import manager_wiring as wiring
from aimilivpn.system import proxy_server
from aimilivpn.system.manager_callbacks import (
    console_token,
    diagnose_with_host_keyword,
    exit_process,
    is_linux,
    module_log_writer,
    print_line,
    set_stderr,
    set_stdout,
)
from aimilivpn.system.manager_config import bounded_int, build_manager_runtime_environment
from aimilivpn.system.manager_helpers import parse_int, safe_name
from aimilivpn.system.manager_web import default_index_html, default_login_html
from aimilivpn.system.openvpn_status import update_handshake_status as update_openvpn_handshake_status
from aimilivpn.system.startup import start_daemon_threads, wait_for_gateway
from aimilivpn.web.api import quality_to_dict, region_to_dict
from aimilivpn.web.server import serve_web_forever


class ManagerRuntimeContext:
    def __init__(self, *, compiled: bool = False) -> None:
        self.environment = build_manager_runtime_environment(compiled=compiled)
        self.root_dir = self.environment.root_dir
        self.config = self.environment.config
        self.api_url = self.config.api_url
        self.fetch_interval_seconds = self.config.fetch_interval_seconds
        self.check_interval_seconds = self.config.check_interval_seconds
        self.target_valid_nodes = self.config.target_valid_nodes
        self.max_scan_rows = self.config.max_scan_rows
        self.openvpn_test_timeout_seconds = self.config.openvpn_test_timeout_seconds
        self.openvpn_maintenance_test_timeout_seconds = self.config.openvpn_maintenance_test_timeout_seconds
        self.node_test_workers = self.config.node_test_workers
        self.max_maintenance_test_nodes = self.config.max_maintenance_test_nodes
        self.node_retest_interval_seconds = self.config.node_retest_interval_seconds
        self.openvpn_cmd = self.config.openvpn_cmd
        self.openvpn_auth_user = self.config.openvpn_auth_user
        self.openvpn_auth_pass = self.config.openvpn_auth_pass
        self.local_proxy_host = self.config.local_proxy_host
        self.local_proxy_port = self.config.local_proxy_port
        self.ui_host = self.config.ui_host
        self.ui_port = self.config.ui_port
        self.invalid_backoff_seconds = self.config.invalid_backoff_seconds
        self.instance_id = self.config.instance_id
        self.tun_dev = self.config.tun_dev
        self.policy_table = self.config.policy_table
        self.allowed_countries = self.config.allowed_countries
        self.exclude_datacenter = self.config.exclude_datacenter
        self.allow_insecure_fetch = self.config.allow_insecure_fetch

        self.runtime_paths = self.environment.paths
        self.data_dir = self.runtime_paths.data_dir
        self.config_dir = self.runtime_paths.config_dir
        self.nodes_file = self.runtime_paths.nodes_file
        self.state_file = self.runtime_paths.state_file
        self.auth_file = self.runtime_paths.auth_file
        self.upstream_proxy_auth_file_path = self.runtime_paths.upstream_proxy_auth_file
        self.blacklist_file = self.runtime_paths.blacklist_file
        self.regions_file = self.runtime_paths.regions_file
        self.quality_results_file = self.runtime_paths.quality_results_file

        self._build_repository_runtime()
        self._build_quality_runtime()
        self._build_shared_state()
        self._build_auth_runtime()
        self._build_ui_runtime()
        self._apply_saved_ui_overrides()
        self._build_runtime_state()
        self._build_runtime_files()
        self._build_thread_runtime()
        self._build_node_view_runtime()
        self._build_proxy_health_runtime()
        self._build_json_log_runtime()
        self._build_fetch_runtime()
        self._build_connection_runtime()
        self._build_monitoring_runtime()
        self._build_web_runtime()
        self._build_openvpn_runtime()
        self._build_service_runtime()
        self._build_entry_runtime()
        self._build_node_probe_runtime()

        self.handler_class = self.manager_entry_runtime.handler_class()

    def _build_repository_runtime(self) -> None:
        context_foundation.build_repository_runtime(self)

    def _build_quality_runtime(self) -> None:
        context_foundation.build_quality_runtime(self)

    def _build_shared_state(self) -> None:
        context_foundation.build_shared_state(self)

    def _build_auth_runtime(self) -> None:
        context_foundation.build_auth_runtime(self)

    def _build_ui_runtime(self) -> None:
        context_foundation.build_ui_runtime(self)

    def _apply_saved_ui_overrides(self) -> None:
        context_foundation.apply_saved_ui_overrides(self)

    def _build_runtime_state(self) -> None:
        context_foundation.build_runtime_state(self)

    def _build_runtime_files(self) -> None:
        context_foundation.build_runtime_files(self)

    def _build_thread_runtime(self) -> None:
        context_support.build_thread_runtime(self)

    def _build_node_view_runtime(self) -> None:
        context_support.build_node_view_runtime(self)

    def _build_proxy_health_runtime(self) -> None:
        context_support.build_proxy_health_runtime(self)

    def _build_json_log_runtime(self) -> None:
        context_support.build_json_log_runtime(self)

    def _build_fetch_runtime(self) -> None:
        context_support.build_fetch_runtime(self)

    def _build_connection_runtime(self) -> None:
        context_connection.build_connection_runtime(self)

    def _build_monitoring_runtime(self) -> None:
        context_connection.build_monitoring_runtime(self)

    def _build_web_runtime(self) -> None:
        context_web.build_web_runtime(self)

    def _build_openvpn_runtime(self) -> None:
        context_process.build_openvpn_runtime(self)

    def _build_service_runtime(self) -> None:
        context_process.build_service_runtime(self)

    def _build_entry_runtime(self) -> None:
        context_process.build_entry_runtime(self)

    def _build_node_probe_runtime(self) -> None:
        context_process.build_node_probe_runtime(self)

    def enrich_quality_with_scamalytics(self, result: QualityResult) -> QualityResult:
        return self.manager_quality_runtime.enrich_quality_with_scamalytics(
            result,
            provider_getter=self.get_scamalytics_provider,
        )

    def record_quality_result_from_probe(
        self,
        node: dict[str, Any],
        openvpn_success: bool | None,
        latency_ms: int,
        probe_message: str = "",
    ) -> QualityResult:
        return self.manager_quality_runtime.record_quality_result_from_probe(
            node,
            openvpn_success,
            latency_ms,
            probe_message,
            provider_getter=self.get_scamalytics_provider,
        )

    def check_quality_ip(self, ip: str) -> QualityResult:
        return self.manager_quality_runtime.check_quality_ip(
            ip,
            provider_getter=self.get_scamalytics_provider,
        )

    def openvpn_command(self, config_file: str, route_nopull: bool, dev: str | None = None) -> list[str]:
        return self.manager_openvpn_runtime.openvpn_command(config_file, route_nopull, dev or self.tun_dev)

    def update_handshake_status(self, line_lower: str) -> None:
        update_openvpn_handshake_status(line_lower, self.set_state)

    def run_openvpn_until_ready(
        self,
        config_file: str,
        keep_alive: bool,
        route_nopull: bool,
        timeout: int | None = None,
        dev: str | None = None,
    ) -> tuple[bool, str, subprocess.Popen[str] | None]:
        return self.manager_openvpn_runtime.run_openvpn_until_ready(
            config_file,
            keep_alive=keep_alive,
            route_nopull=route_nopull,
            timeout=timeout,
            dev=dev or self.tun_dev,
        )

    def test_multiple_nodes(
        self,
        node_ids: list[str],
        timeout: int | None = None,
        max_workers: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.manager_node_probe_runtime.test_multiple_nodes(
            node_ids,
            timeout=timeout if timeout is not None else self.openvpn_maintenance_test_timeout_seconds,
            max_workers=max_workers if max_workers is not None else self.node_test_workers,
        )

    def auto_switch_node(self, attempt: int = 0) -> None:
        self.connection_orchestrator().auto_switch_node(attempt)

    def connect_node(self, node_id: str) -> str:
        return self.connection_orchestrator().connect_node(node_id)

    def maintain_valid_nodes(self, force: bool = False) -> str:
        return self.connection_orchestrator().maintain_valid_nodes(force)

    def main(self) -> None:
        self.manager_entry_runtime.main()


def build_manager_runtime_context(*, compiled: bool = False) -> ManagerRuntimeContext:
    return ManagerRuntimeContext(compiled=compiled)
