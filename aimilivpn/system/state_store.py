from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from aimilivpn.core.connection_state import normalize_connection_phase
from aimilivpn.system.startup import format_proxy_url


def write_json_file(path: Path, data: Any, lock: Any) -> None:
    with lock:
        path.parent.mkdir(exist_ok=True, parents=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _chmod_private(tmp)
        tmp.replace(path)
        _chmod_private(path)


def read_json_file(path: Path, default: Any, lock: Any) -> Any:
    with lock:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default


@dataclass(frozen=True)
class RuntimeStateStore:
    state_file: Path
    lock: Any
    active_node_id: Callable[[], str]
    is_connecting: Callable[[], bool]
    load_ui_config: Callable[[], dict[str, Any]]
    api_url: str
    instance_id: str
    tun_dev: str
    policy_table: str
    allowed_countries: Iterable[str]
    target_valid_nodes: int
    fetch_interval_seconds: int
    check_interval_seconds: int
    local_proxy_host: str
    local_proxy_port: int

    def get_state(self) -> dict[str, Any]:
        state = read_json_file(self.state_file, {}, self.lock)
        state.pop("password", None)
        state["active_openvpn_node_id"] = self.active_node_id()
        state["is_connecting"] = self.is_connecting()
        state["connection_state"] = normalize_connection_phase(
            state.get("connection_state"),
            is_connecting=state["is_connecting"],
            active_node_id=state["active_openvpn_node_id"],
        )
        state.setdefault("api_url", self.api_url)
        state["instance_id"] = self.instance_id
        state["tun_dev"] = self.tun_dev
        state["policy_table"] = self.policy_table
        state["allowed_countries"] = sorted(self.allowed_countries)
        state.setdefault("target_valid_nodes", self.target_valid_nodes)
        state.setdefault("fetch_interval_seconds", self.fetch_interval_seconds)
        state.setdefault("check_interval_seconds", self.check_interval_seconds)
        state["local_proxy"] = format_proxy_url(self.local_proxy_host, self.local_proxy_port)
        state.setdefault("last_fetch_status", "not_started")
        state.setdefault("last_check_message", "")
        state.setdefault("blacklisted_nodes", 0)

        ui_config = self.load_ui_config()
        state["username"] = ui_config.get("username", "admin")
        state["port"] = ui_config.get("port", 8787)
        state["secret_path"] = ui_config.get("secret_path", "EJsW2EeBo9lY")
        state["password_set"] = bool(ui_config.get("password_hash"))
        state["proxy_port"] = ui_config.get("proxy_port", 7928)
        state["routing_mode"] = ui_config.get("routing_mode", "auto")
        state["force_country"] = ui_config.get("force_country", "")
        state["routing_ip_type"] = ui_config.get("routing_ip_type", "all")
        state["connection_enabled"] = ui_config.get("connection_enabled", True)
        state["fixed_node_id"] = ui_config.get("fixed_node_id", "")
        state["favorite_node_ids"] = ui_config.get("favorite_node_ids", [])
        state["fav_fail_fallback"] = ui_config.get("fav_fail_fallback", True)
        return state

    def set_state(self, **updates: Any) -> None:
        state = self.get_state()
        state.update(updates)
        write_json_file(self.state_file, state, self.lock)


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass
