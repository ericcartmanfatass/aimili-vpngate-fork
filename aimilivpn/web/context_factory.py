from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.web.route_contexts import (
    ApiGetRouteContext,
    ApiMutationRouteContext,
    ApiPostRouteContext,
    AuthRouteContext,
    ConfigRouteContext,
    LogsRouteContext,
    NodeRouteContext,
    PageRouteContext,
    ProxyRouteContext,
    RegionQualityRouteContext,
    StatusRouteContext,
)


@dataclass(frozen=True)
class WebRouteContextFactory:
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
    save_ui_config: Callable[[dict[str, Any]], None]
    maintain_valid_nodes: Callable[[bool], str]
    maintenance_running: Callable[[], bool]
    start_maintenance: Callable[[], None]
    validate_routing_region_target: Callable[[str, str], None]
    clear_sessions: Callable[[], None]
    schedule_restart: Callable[[str], None]
    verify_password: Callable[[str, str], bool]
    verify_username: Callable[[str, str], bool]
    generate_session_token: Callable[[], str]
    add_session: Callable[[str, float], None]
    remove_session: Callable[[str], None]
    check_proxy_health: Callable[[], dict[str, Any]]
    ui_host: str
    ui_port: int
    proxy_host: str
    proxy_port: int
    proxy_gateway_status: Callable[[], tuple[bool, str]]
    active_openvpn_running: Callable[[], bool]
    is_linux: Callable[[], bool]
    tun_dev: str
    tun_exists: Callable[[], bool]
    server_start_time: float
    last_collector_heartbeat: Callable[[], float]
    last_checker_heartbeat: Callable[[], float]
    last_pinger_heartbeat: Callable[[], float]
    check_interval_seconds: int
    format_local_time: Callable[[float], str]
    read_log_entries: Callable[[], list[dict[str, Any]]]
    login_html_fallback: str
    index_html_fallback: str
    submit_operation: Callable[[str, str, Callable[[], Any], bool], tuple[dict[str, Any], bool]] | None = None
    get_operation: Callable[[str], dict[str, Any] | None] | None = None
    list_operations: Callable[[], list[dict[str, Any]]] | None = None

    def region_quality(self) -> RegionQualityRouteContext:
        return RegionQualityRouteContext(
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
            submit_operation=self.submit_operation,
        )

    def node(self) -> NodeRouteContext:
        return NodeRouteContext(
            read_nodes=self.read_nodes,
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
            test_node_by_id=self.test_node_by_id,
            connect_node=self.connect_node,
            stop_active_openvpn=self.stop_active_openvpn,
            load_ui_config=self.load_ui_config,
            save_ui_config=self.save_ui_config,
            maintain_valid_nodes=self.maintain_valid_nodes,
            maintenance_running=self.maintenance_running,
            start_maintenance=self.start_maintenance,
            submit_operation=self.submit_operation,
            get_operation=self.get_operation,
            list_operations=self.list_operations,
        )

    def config(self) -> ConfigRouteContext:
        return ConfigRouteContext(
            load_ui_config=self.load_ui_config,
            save_ui_config=self.save_ui_config,
            validate_routing_region_target=self.validate_routing_region_target,
            clear_sessions=self.clear_sessions,
            schedule_restart=self.schedule_restart,
        )

    def auth(self, get_secret_path: Callable[[], str]) -> AuthRouteContext:
        return AuthRouteContext(
            load_ui_config=self.load_ui_config,
            verify_password=self.verify_password,
            verify_username=self.verify_username,
            generate_session_token=self.generate_session_token,
            add_session=self.add_session,
            remove_session=self.remove_session,
            get_secret_path=get_secret_path,
            now=self.now,
        )

    def proxy(self) -> ProxyRouteContext:
        return ProxyRouteContext(
            check_proxy_health=self.check_proxy_health,
            set_state=self.set_state,
        )

    def status(self) -> StatusRouteContext:
        return StatusRouteContext(
            load_ui_config=self.load_ui_config,
            ui_host=self.ui_host,
            ui_port=self.ui_port,
            proxy_host=self.proxy_host,
            proxy_port=self.proxy_port,
            proxy_gateway_status=self.proxy_gateway_status,
            active_openvpn_running=self.active_openvpn_running,
            active_node_id=self.get_active_node_id,
            is_linux=self.is_linux,
            tun_dev=self.tun_dev,
            tun_exists=self.tun_exists,
            now=self.now,
            server_start_time=self.server_start_time,
            last_collector_heartbeat=self.last_collector_heartbeat,
            last_checker_heartbeat=self.last_checker_heartbeat,
            last_pinger_heartbeat=self.last_pinger_heartbeat,
            check_interval_seconds=self.check_interval_seconds,
            format_local_time=self.format_local_time,
        )

    def logs(self) -> LogsRouteContext:
        return LogsRouteContext(read_log_entries=self.read_log_entries)

    def page(self, is_authorized: Callable[[], bool]) -> PageRouteContext:
        return PageRouteContext(
            is_authorized=is_authorized,
            login_html_fallback=self.login_html_fallback,
            index_html_fallback=self.index_html_fallback,
        )

    def api_get(self) -> ApiGetRouteContext:
        return ApiGetRouteContext(
            region_quality=self.region_quality(),
            node=self.node(),
            status=self.status(),
            logs=self.logs(),
        )

    def api_post(
        self,
        get_secret_path: Callable[[], str],
        is_authorized: Callable[[], bool],
    ) -> ApiPostRouteContext:
        return ApiPostRouteContext(
            auth=self.auth(get_secret_path),
            region_quality=self.region_quality(),
            node=self.node(),
            config=self.config(),
            proxy=self.proxy(),
            is_authorized=is_authorized,
        )

    def api_mutation(self, is_authorized: Callable[[], bool]) -> ApiMutationRouteContext:
        return ApiMutationRouteContext(
            region_quality=self.region_quality(),
            is_authorized=is_authorized,
            config=self.config(),
        )
