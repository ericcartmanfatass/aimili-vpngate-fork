from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.connection_state import ConnectionPhase
from aimilivpn.system import connection_connect, connection_maintenance, connection_switching
from aimilivpn.system.connection_runtime import ActiveConnectionRuntimeFacade


@dataclass
class ConnectionOrchestrator:
    connection_runtime: Callable[[], ActiveConnectionRuntimeFacade]
    ensure_dirs: Callable[[], None]
    run_locked: Callable[[Callable[[], Any]], Any]
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    load_ui_config: Callable[[], dict[str, Any]]
    set_state: Callable[..., None]
    log_line: Callable[[str, str, str], None]
    print_line: Callable[[str], None]
    start_thread: Callable[[Callable[[], None]], None]
    try_acquire_maintenance: Callable[[], bool]
    release_maintenance: Callable[[], None]
    get_is_connecting: Callable[[], bool]
    set_is_connecting: Callable[[bool], None]
    get_active_node_id: Callable[[], str]
    set_active_node_id: Callable[[str], None]
    get_last_active_latency: Callable[[], int]
    set_last_active_latency: Callable[[int], None]
    set_last_active_ping_time: Callable[[float], None]
    set_active_connection: Callable[[Any, str], None]
    node_matches_allowed: Callable[[dict[str, Any]], bool]
    allowed_countries: Callable[[], set[str]]
    filter_nodes_by_routing_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    routing_target_label: Callable[[str], str]
    parse_int: Callable[[Any], int]
    ping_latency_ms: Callable[[str, int, int], int]
    write_ovpn_config: Callable[[Path, str], None]
    run_openvpn_until_ready: Callable[[str], tuple[bool, str, Any]]
    stop_active_openvpn: Callable[[], None]
    active_openvpn_running: Callable[[], bool]
    setup_policy_routing: Callable[[str], None]
    check_proxy_health: Callable[[], dict[str, Any]]
    clear_active_connection_state: Callable[[str], None]
    fetch_candidates: Callable[[], list[dict[str, Any]]]
    check_and_fix_dns: Callable[[], None]
    diagnose_api_failure: Callable[[str], tuple[Any, Any]]
    select_maintenance_test_nodes: Callable[[list[dict[str, Any]]], list[str]]
    test_multiple_nodes: Callable[[list[str]], list[dict[str, Any]]]
    now: Callable[[], float]
    api_url: Callable[[], str]
    tun_dev: Callable[[], str]
    proxy_host: Callable[[], str]
    proxy_port: Callable[[], int]
    maintenance_test_limit: Callable[[], int]
    node_test_workers: Callable[[], int]
    exclude_datacenter: Callable[[], bool]
    set_connection_phase: Callable[[ConnectionPhase | str, str, str], None] | None = None
    wait_for_stop: Callable[[float], bool] | None = None
    instance_retry_backoff_seconds: tuple[int, ...] = (60, 300, 900, 1800)
    connection_candidate_limit: int = 3
    mark_blacklisted: Callable[[dict[str, Any], str], None] | None = None
    get_state: Callable[[], dict[str, Any]] | None = None
    _switch_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _retry_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _retry_scheduled: bool = field(default=False, init=False, repr=False)
    _retry_generation: int = field(default=0, init=False, repr=False)
    _last_no_candidate_message: str = field(default="", init=False, repr=False)

    def transition(self, phase: ConnectionPhase, message: str = "", node_id: str = "") -> None:
        if self.set_connection_phase is not None:
            self.set_connection_phase(phase, message, node_id)

    def auto_switch_node(self, attempt: int = 0) -> None:
        if self.retry_scheduled():
            if self.load_ui_config().get("connection_enabled", True):
                return
            self.cancel_retry_scheduled()
        if not self._switch_lock.acquire(blocking=False):
            return
        try:
            connection_switching.auto_switch_node(self, attempt)
        finally:
            self._switch_lock.release()

    def retry_scheduled(self) -> bool:
        with self._retry_lock:
            return self._retry_scheduled

    def mark_retry_scheduled(self) -> bool:
        with self._retry_lock:
            if self._retry_scheduled:
                return False
            self._retry_scheduled = True
            self._retry_generation += 1
            return True

    def clear_retry_scheduled(self) -> None:
        with self._retry_lock:
            self._retry_scheduled = False

    def cancel_retry_scheduled(self) -> None:
        with self._retry_lock:
            self._retry_scheduled = False
            self._retry_generation += 1

    def retry_generation(self) -> int:
        with self._retry_lock:
            return self._retry_generation

    def retry_generation_is_current(self, generation: int) -> bool:
        with self._retry_lock:
            return generation == self._retry_generation

    def should_log_no_candidate(self, message: str) -> bool:
        with self._retry_lock:
            if self._last_no_candidate_message == message:
                return False
            self._last_no_candidate_message = message
            return True

    def clear_no_candidate_suppression(self) -> None:
        with self._retry_lock:
            self._last_no_candidate_message = ""

    def connect_node(self, node_id: str) -> str:
        return connection_connect.connect_node(self, node_id)

    def maintain_valid_nodes(self, force: bool = False) -> str:
        return connection_maintenance.maintain_valid_nodes(self, force)

    def _recover_interrupted_connection(self) -> None:
        connection_maintenance.recover_interrupted_connection(self)

    def _merge_candidate_nodes(self, candidates: list[dict[str, Any]]) -> None:
        connection_maintenance.merge_candidates(self, candidates)

    def _finish_maintenance_cycle(self) -> dict[str, Any]:
        return connection_maintenance.finish_maintenance_cycle(self)
