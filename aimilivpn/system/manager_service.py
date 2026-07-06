from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from aimilivpn.system.service_runtime import Tee, VpnGateServiceRuntime
from aimilivpn.system.startup import DaemonTask


@dataclass
class ManagerServiceRuntime:
    ensure_dirs: Callable[[], None]
    kill_existing_openvpn_processes: Callable[[], None]
    data_dir: Callable[[], Path]
    state_file: Callable[[], Path]
    write_json: Callable[[Path, Any], None]
    api_url: Callable[[], str]
    instance_id: Callable[[], str]
    tun_dev: Callable[[], str]
    policy_table: Callable[[], str]
    allowed_countries: Callable[[], set[str]]
    target_valid_nodes: Callable[[], int]
    fetch_interval_seconds: Callable[[], int]
    check_interval_seconds: Callable[[], int]
    local_proxy_host: Callable[[], str]
    local_proxy_port: Callable[[], int]
    ui_host: Callable[[], str]
    ui_port: Callable[[], int]
    start_proxy_server: Callable[[str, int, str], None]
    collector_loop: Callable[[], None]
    background_proxy_checker: Callable[[], None]
    active_node_pinger: Callable[[], None]
    start_daemon_threads: Callable[[Iterable[DaemonTask]], None]
    wait_for_gateway: Callable[[str, int], bool]
    load_ui_config: Callable[[], dict[str, Any]]
    bounded_int: Callable[[Any, int, int, int], int]
    web_server_runtime: Callable[[], Any]
    serve_web_forever: Callable[[str, int, Any], None]
    print_line: Callable[[str], None]
    set_stdout: Callable[[Any], None]
    set_stderr: Callable[[Any], None]
    tee_factory: Callable[[str], Any] = Tee
    _runtime: VpnGateServiceRuntime | None = field(default=None, init=False)

    def runtime(self) -> VpnGateServiceRuntime:
        if self._runtime is None:
            self._runtime = VpnGateServiceRuntime(
                ensure_dirs=self.ensure_dirs,
                kill_existing_openvpn_processes=self.kill_existing_openvpn_processes,
                data_dir=self.data_dir,
                state_file=self.state_file,
                write_json=self.write_json,
                api_url=self.api_url,
                instance_id=self.instance_id,
                tun_dev=self.tun_dev,
                policy_table=self.policy_table,
                allowed_countries=self.allowed_countries,
                target_valid_nodes=self.target_valid_nodes,
                fetch_interval_seconds=self.fetch_interval_seconds,
                check_interval_seconds=self.check_interval_seconds,
                local_proxy_host=self.local_proxy_host,
                local_proxy_port=self.local_proxy_port,
                ui_host=self.ui_host,
                ui_port=self.ui_port,
                start_proxy_server=self.start_proxy_server,
                collector_loop=self.collector_loop,
                background_proxy_checker=self.background_proxy_checker,
                active_node_pinger=self.active_node_pinger,
                start_daemon_threads=self.start_daemon_threads,
                wait_for_gateway=self.wait_for_gateway,
                load_ui_config=self.load_ui_config,
                bounded_int=self.bounded_int,
                web_server_runtime=self.web_server_runtime,
                serve_web_forever=self.serve_web_forever,
                print_line=self.print_line,
                set_stdout=self.set_stdout,
                set_stderr=self.set_stderr,
                tee_factory=self.tee_factory,
            )
        return self._runtime

    def main(self) -> None:
        self.runtime().main()
