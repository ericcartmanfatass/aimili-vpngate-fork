from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.connection import connection_failure_state, mark_connection_failed, prepare_connection_target
from aimilivpn.core.connection_state import ConnectionPhase


@dataclass
class ActiveConnectionRuntimeFacade:
    cleanup_policy_routing: Callable[[], None]
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    load_ui_config: Callable[[], dict[str, Any]]
    save_ui_config: Callable[[dict[str, Any]], None]
    find_active_config_file: Callable[[list[dict[str, Any]], str], str | None]
    clear_active_flags: Callable[[list[dict[str, Any]]], None]
    stop_process: Callable[[subprocess.Popen[str] | None], None]
    kill_existing_processes: Callable[[], None]
    delete_file_if_exists: Callable[[str | Path | None], bool]
    set_state: Callable[..., None]
    run_exclusive: Callable[[Callable[[], None]], None]
    log_line: Callable[[str, str], None] | None = None
    print_line: Callable[[str], None] = print
    inactive_latency_label: str = "无活动连接"
    set_connection_phase: Callable[[ConnectionPhase | str, str, str], None] | None = None

    def transition(self, phase: ConnectionPhase, message: str = "", node_id: str = "") -> None:
        if self.set_connection_phase is not None:
            self.set_connection_phase(phase, message, node_id)

    def begin_connect(
        self,
        *,
        node_id: str,
        is_connecting: bool,
        busy_log_message: str,
        busy_error_message: str,
        active_node_latency: str,
        last_check_message: str,
    ) -> bool:
        if is_connecting:
            self.print_line(busy_log_message)
            raise RuntimeError(busy_error_message)
        self.set_state(
            is_connecting=True,
            active_node_latency=active_node_latency,
            last_check_message=last_check_message.format(node_id=node_id),
        )
        self.transition(ConnectionPhase.CONNECTING, last_check_message.format(node_id=node_id), node_id)
        return True

    def finish_connecting(self) -> bool:
        return False

    def prepare_target(
        self,
        node_id: str,
        *,
        node_matches_allowed: Callable[[dict[str, Any]], bool],
        allowed_countries: set[str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        nodes = self.read_nodes()
        ui_config = self.load_ui_config()
        node, ui_config = prepare_connection_target(
            nodes,
            node_id,
            ui_config,
            node_matches_allowed=node_matches_allowed,
            allowed_countries=allowed_countries,
        )
        self.run_exclusive(lambda: self.save_ui_config(ui_config))
        return nodes, node

    def handle_start_failure(
        self,
        *,
        nodes: list[dict[str, Any]],
        node_id: str,
        config_path: str | Path,
        message: str,
        log_message_template: str,
        print_message_template: str,
    ) -> str:
        self.delete_file_if_exists(config_path)
        mark_connection_failed(nodes, node_id, message=message)
        self.write_nodes(nodes)
        if self.log_line:
            self.log_line("ERROR", log_message_template.format(node_id=node_id, message=message))
        self.print_line(print_message_template.format(node_id=node_id, message=message))
        self.set_state(**connection_failure_state("无法建立连接"))
        self.transition(ConnectionPhase.FAILED, "连接失败")
        return ""

    def register_active_process(
        self,
        process: subprocess.Popen[str],
        node_id: str,
    ) -> tuple[subprocess.Popen[str], str]:
        return process, node_id

    def stop_active(
        self,
        process: subprocess.Popen[str] | None,
        node_id: str,
    ) -> tuple[subprocess.Popen[str] | None, str]:
        self.cleanup_policy_routing()
        config_to_delete = None
        if node_id:
            nodes = self.read_nodes()
            config_to_delete = self.find_active_config_file(nodes, node_id)

        self.stop_process(process)
        self.kill_existing_processes()
        self.delete_file_if_exists(config_to_delete)
        return None, ""

    def is_running(self, process: subprocess.Popen[str] | None) -> bool:
        return process is not None and process.poll() is None

    def clear_active_state(
        self,
        process: subprocess.Popen[str] | None,
        message: str,
    ) -> tuple[subprocess.Popen[str] | None, str]:
        self.stop_process(process)

        def clear_nodes() -> None:
            nodes = self.read_nodes()
            self.clear_active_flags(nodes)
            self.write_nodes(nodes)

        self.run_exclusive(clear_nodes)
        self.set_state(
            active_openvpn_node_id="",
            is_connecting=False,
            active_node_latency=self.inactive_latency_label,
            last_check_message=message,
        )
        self.transition(ConnectionPhase.FAILED, message)
        return None, ""
