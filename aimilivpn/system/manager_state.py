from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ManagerMutableState:
    active_sessions: dict[str, float] = field(default_factory=dict)
    active_openvpn_process: Any | None = None
    active_openvpn_node_id: str = ""
    is_connecting: bool = True
    last_active_ping_time: float = 0.0
    last_active_latency: int = 0
    last_collector_heartbeat: float = 0.0
    last_checker_heartbeat: float = 0.0
    last_pinger_heartbeat: float = 0.0
    server_start_time: float = field(default_factory=time.time)

    def active_node_id(self) -> str:
        return str(self.active_openvpn_node_id or "")

    def set_active_connection(self, process: Any, node_id: str) -> None:
        self.active_openvpn_process = process
        self.active_openvpn_node_id = node_id

    def set_last_active_ping_time(self, value: float) -> None:
        self.last_active_ping_time = value

    def set_last_active_latency(self, value: int) -> None:
        self.last_active_latency = value
