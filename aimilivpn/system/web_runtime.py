from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, MutableMapping

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.web.context_factory import WebRouteContextFactory
from aimilivpn.web.server import WebServerRuntime
from aimilivpn.web.status import probe_proxy_gateway, read_json_log_entries


@dataclass
class WebRuntimeWiring:
    region_repository: Any
    read_regions: Callable[[], list[RegionProfile]]
    read_nodes: Callable[[], list[dict[str, Any]]]
    region_from_payload: Callable[[dict[str, Any], RegionProfile | None], RegionProfile]
    quality_provider_status: Callable[[], dict[str, Any]]
    latest_quality_for_node: Callable[[str], QualityResult | None]
    latest_quality_map: Callable[[], dict[str, QualityResult]]
    test_node_by_id: Callable[[str], dict[str, Any]]
    check_quality_ip: Callable[[str], QualityResult]
    check_quality_region: Callable[[str, int], dict[str, Any]]
    bounded_int: Callable[[Any, int, int, int], int]
    scamalytics_errors: tuple[type[BaseException], ...]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    filter_nodes_by_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    get_state: Callable[[], dict[str, Any]]
    set_state: Callable[..., None]
    get_active_node_id: Callable[[], str]
    get_last_active_ping_time: Callable[[], float]
    set_last_active_ping_time: Callable[[float], None]
    get_last_active_latency: Callable[[], int]
    set_last_active_latency: Callable[[int], None]
    now: Callable[[], float]
    ping_latency_ms: Callable[[str, int, int], int]
    parse_int: Callable[[Any], int]
    start_daemon_thread: Callable[[Callable[..., None], tuple[Any, ...]], None]
    test_multiple_nodes: Callable[[Any], list[dict[str, Any]]]
    connect_node: Callable[[str], str]
    stop_active_openvpn: Callable[[], None]
    load_ui_config: Callable[[], dict[str, Any]]
    save_ui_config_unlocked: Callable[[dict[str, Any]], None]
    maintain_valid_nodes: Callable[[bool], str]
    maintenance_running: Callable[[], bool]
    start_maintenance: Callable[[], None]
    validate_routing_region_target: Callable[[str, str], None]
    verify_password: Callable[[str, str], bool]
    verify_username: Callable[[str, str], bool]
    generate_session_token: Callable[[], str]
    check_proxy_health: Callable[[], dict[str, Any]]
    ui_host: Callable[[], str]
    ui_port: Callable[[], int]
    trust_proxy_headers: Callable[[], bool]
    trusted_proxy_addresses: Callable[[], tuple[str, ...]]
    proxy_host: Callable[[], str]
    proxy_port: Callable[[], int]
    active_openvpn_running: Callable[[], bool]
    is_linux: Callable[[], bool]
    tun_dev: Callable[[], str]
    server_start_time: Callable[[], float]
    last_collector_heartbeat: Callable[[], float]
    last_checker_heartbeat: Callable[[], float]
    last_pinger_heartbeat: Callable[[], float]
    check_interval_seconds: Callable[[], int]
    login_html_fallback: Callable[[], str]
    index_html_fallback: Callable[[], str]
    active_sessions: MutableMapping[str, float]
    lock: Any
    data_dir: Callable[[], Path]
    console_token: Callable[[], str]
    diagnose_local_obstructions: Callable[[int, str], tuple[bool, str] | None]
    start_thread: Callable[[Callable[[], None]], None]
    sleep: Callable[[int | float], None]
    exit_process: Callable[[int], None]
    print_line: Callable[[str], None]

    def clear_active_sessions(self) -> None:
        with self.lock:
            self.active_sessions.clear()

    def schedule_server_restart(self, message: str) -> None:
        def restart_server() -> None:
            self.sleep(2)
            self.print_line(f"[系统] {message}")
            self.exit_process(0)

        self.start_thread(restart_server)

    def save_ui_config_locked(self, config: dict[str, Any]) -> None:
        with self.lock:
            self.save_ui_config_unlocked(config)

    def add_active_session(self, token: str, expires_at: float) -> None:
        with self.lock:
            self.active_sessions[token] = expires_at

    def remove_active_session(self, token: str) -> None:
        with self.lock:
            self.active_sessions.pop(token, None)

    def proxy_gateway_status(self) -> tuple[bool, str]:
        host = self.proxy_host()
        return probe_proxy_gateway(
            host,
            self.proxy_port(),
            lambda port: self.diagnose_local_obstructions(port, host),
        )

    def read_api_log_entries(self) -> list[dict[str, Any]]:
        return read_json_log_entries(
            self.data_dir() / "logs",
            lock=self.lock,
            on_error=lambda exc: self.print_line(f"[API Logs] Error reading log file: {exc}"),
        )

    def route_context_factory(self) -> WebRouteContextFactory:
        return WebRouteContextFactory(
            region_repository=self.region_repository,
            read_regions=self.read_regions,
            read_nodes=self.read_nodes,
            region_from_payload=self.region_from_payload,
            quality_provider_status=self.quality_provider_status,
            latest_quality_for_node=self.latest_quality_for_node,
            latest_quality_map=self.latest_quality_map,
            test_node_by_id=self.test_node_by_id,
            check_quality_ip=self.check_quality_ip,
            check_quality_region=self.check_quality_region,
            bounded_int=self.bounded_int,
            scamalytics_errors=self.scamalytics_errors,
            write_nodes=self.write_nodes,
            filter_nodes_by_region=self.filter_nodes_by_region,
            get_state=self.get_state,
            set_state=self.set_state,
            get_active_node_id=self.get_active_node_id,
            get_last_active_ping_time=self.get_last_active_ping_time,
            set_last_active_ping_time=self.set_last_active_ping_time,
            get_last_active_latency=self.get_last_active_latency,
            set_last_active_latency=self.set_last_active_latency,
            now=self.now,
            ping_latency_ms=self.ping_latency_ms,
            parse_int=self.parse_int,
            start_daemon_thread=self.start_daemon_thread,
            test_multiple_nodes=self.test_multiple_nodes,
            connect_node=self.connect_node,
            stop_active_openvpn=self.stop_active_openvpn,
            load_ui_config=self.load_ui_config,
            save_ui_config=self.save_ui_config_locked,
            maintain_valid_nodes=self.maintain_valid_nodes,
            maintenance_running=self.maintenance_running,
            start_maintenance=self.start_maintenance,
            validate_routing_region_target=self.validate_routing_region_target,
            clear_sessions=self.clear_active_sessions,
            schedule_restart=self.schedule_server_restart,
            verify_password=self.verify_password,
            verify_username=self.verify_username,
            generate_session_token=self.generate_session_token,
            add_session=self.add_active_session,
            remove_session=self.remove_active_session,
            check_proxy_health=self.check_proxy_health,
            ui_host=self.ui_host(),
            ui_port=self.ui_port(),
            proxy_host=self.proxy_host(),
            proxy_port=self.proxy_port(),
            proxy_gateway_status=self.proxy_gateway_status,
            active_openvpn_running=self.active_openvpn_running,
            is_linux=self.is_linux,
            tun_dev=self.tun_dev(),
            tun_exists=lambda: Path(f"/sys/class/net/{self.tun_dev()}").exists(),
            server_start_time=self.server_start_time(),
            last_collector_heartbeat=self.last_collector_heartbeat,
            last_checker_heartbeat=self.last_checker_heartbeat,
            last_pinger_heartbeat=self.last_pinger_heartbeat,
            check_interval_seconds=self.check_interval_seconds(),
            format_local_time=self.format_local_time,
            read_log_entries=self.read_api_log_entries,
            login_html_fallback=self.login_html_fallback(),
            index_html_fallback=self.index_html_fallback(),
        )

    def web_server_runtime(self) -> WebServerRuntime:
        return WebServerRuntime(
            load_ui_config=self.load_ui_config,
            route_context_factory=self.route_context_factory,
            active_sessions=self.active_sessions,
            session_lock=self.lock,
            console_token=self.console_token,
            trust_proxy_headers=self.trust_proxy_headers(),
            trusted_proxy_addresses=self.trusted_proxy_addresses(),
        )

    @staticmethod
    def format_local_time(value: float) -> str:
        import time

        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
