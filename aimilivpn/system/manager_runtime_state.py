from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.system.state_store import RuntimeStateStore, read_json_file, write_json_file


@dataclass
class ManagerRuntimeState:
    state_file: Callable[[], Path]
    lock: Any
    mutable_state: ManagerMutableState
    load_ui_config: Callable[[], dict[str, Any]]
    api_url: Callable[[], str]
    instance_id: Callable[[], str]
    tun_dev: Callable[[], str]
    policy_table: Callable[[], str]
    allowed_countries: Callable[[], Iterable[str]]
    target_valid_nodes: Callable[[], int]
    fetch_interval_seconds: Callable[[], int]
    check_interval_seconds: Callable[[], int]
    local_proxy_host: Callable[[], str]
    local_proxy_port: Callable[[], int]

    def write_json(self, path: Path, data: Any) -> None:
        write_json_file(path, data, self.lock)

    def read_json(self, path: Path, default: Any) -> Any:
        return read_json_file(path, default, self.lock)

    def store(self) -> RuntimeStateStore:
        return RuntimeStateStore(
            state_file=self.state_file(),
            lock=self.lock,
            active_node_id=self.mutable_state.active_node_id,
            is_connecting=lambda: self.mutable_state.is_connecting,
            load_ui_config=self.load_ui_config,
            api_url=self.api_url(),
            instance_id=self.instance_id(),
            tun_dev=self.tun_dev(),
            policy_table=self.policy_table(),
            allowed_countries=self.allowed_countries(),
            target_valid_nodes=self.target_valid_nodes(),
            fetch_interval_seconds=self.fetch_interval_seconds(),
            check_interval_seconds=self.check_interval_seconds(),
            local_proxy_host=self.local_proxy_host(),
            local_proxy_port=self.local_proxy_port(),
        )

    def get_state(self) -> dict[str, Any]:
        return self.store().get_state()

    def set_state(self, **updates: Any) -> None:
        self.store().set_state(**updates)
