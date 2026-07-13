from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from aimilivpn.system.startup import DaemonTask, build_initial_state


class Tee:
    def __init__(self, file_path: str, stdout: Any | None = None):
        Path(file_path).parent.mkdir(exist_ok=True, parents=True)
        self.file = open(file_path, "a", encoding="utf-8")
        self.stdout = stdout if stdout is not None else sys.stdout

    def write(self, data: str) -> None:
        self.stdout.write(data)
        self.file.write(data)
        self.file.flush()

    def flush(self) -> None:
        self.stdout.flush()
        self.file.flush()

    def isatty(self) -> bool:
        return self.stdout.isatty()

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.stdout, attr)


@dataclass
class VpnGateServiceRuntime:
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
    shutdown_background_threads: Callable[[], None]
    stop_active_openvpn: Callable[[], None]
    tee_factory: Callable[[str], Any] = Tee

    def main(self) -> None:
        self.ensure_dirs()
        self.kill_existing_openvpn_processes()

        tee = self.tee_factory(str(self.data_dir() / "vpngate.log"))
        self.set_stdout(tee)
        self.set_stderr(tee)

        try:
            self.write_json(
                self.state_file(),
                build_initial_state(
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
                    last_check_message="服务已启动，正在初始化网络并获取候选 VPN 节点...",
                    active_node_latency="正在准备",
                ),
            )
            self.start_daemon_threads(((self.start_proxy_server, (self.local_proxy_host(), self.local_proxy_port(), self.tun_dev())),))

            self.print_line("[网关] 正在启动代理网关...")
            gateway_ready = self.wait_for_gateway(self.local_proxy_host(), self.local_proxy_port())
            if gateway_ready:
                self.print_line("[网关] 代理网关已成功启动监听，启动同步与检测脚本...")
            else:
                self.print_line("[警告] 代理网关启动超时，继续执行脚本...")

            self.start_daemon_threads(
                (
                    (self.collector_loop, ()),
                    (self.background_proxy_checker, ()),
                    (self.active_node_pinger, ()),
                )
            )

            ui_cfg = self.load_ui_config()
            ui_host = ui_cfg.get("host", self.ui_host())
            ui_port = self.bounded_int(ui_cfg.get("port"), self.ui_port(), 1, 65535)

            self.print_line(f"UI: http://{ui_host}:{ui_port}/")
            self.print_line(f"Proxy: http://{self.local_proxy_host()}:{self.local_proxy_port()}")
            self.serve_web_forever(ui_host, ui_port, self.web_server_runtime())
        finally:
            self.shutdown_background_threads()
            self.stop_active_openvpn()
