from __future__ import annotations

from enum import Enum
from typing import Any


class ConnectionPhase(str, Enum):
    IDLE = "idle"
    FETCHING = "fetching"
    PROBING = "probing"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SWITCHING = "switching"
    FAILED = "failed"


def normalize_connection_phase(value: Any, *, is_connecting: bool = False, active_node_id: str = "") -> str:
    try:
        raw = value.value if isinstance(value, ConnectionPhase) else str(value or "")
        return ConnectionPhase(raw).value
    except ValueError:
        if is_connecting:
            return ConnectionPhase.CONNECTING.value
        if active_node_id:
            return ConnectionPhase.CONNECTED.value
        return ConnectionPhase.IDLE.value


def connection_phase_update(
    phase: ConnectionPhase | str,
    *,
    message: str = "",
    node_id: str = "",
) -> dict[str, Any]:
    raw = phase.value if isinstance(phase, ConnectionPhase) else str(phase)
    normalized = ConnectionPhase(raw).value
    update: dict[str, Any] = {
        "connection_state": normalized,
        "is_connecting": normalized in {
            ConnectionPhase.FETCHING.value,
            ConnectionPhase.PROBING.value,
            ConnectionPhase.CONNECTING.value,
            ConnectionPhase.SWITCHING.value,
        },
    }
    if message:
        update["last_check_message"] = message
    if node_id or normalized == ConnectionPhase.IDLE.value:
        update["active_openvpn_node_id"] = node_id
    return update
