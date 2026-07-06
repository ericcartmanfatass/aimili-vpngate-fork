from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import subprocess

from aimilivpn.system.openvpn_runtime import OpenVPNRuntimeFacade
from aimilivpn.system.policy_routing import PolicyRoutingFacade


@dataclass
class ManagerOpenVPNRuntime:
    openvpn_cmd: str
    auth_file: Path
    data_dir: Path
    config_dir: Path
    upstream_proxy_auth_path: Path
    root_dir: Path
    default_dev: Callable[[], str]
    policy_table: Callable[[], str]
    default_timeout_seconds: Callable[[], int]
    get_upstream_proxy: Callable[[], tuple[str | None, str | None, int | None]]
    write_upstream_proxy_auth_file: Callable[[], str | None]
    diagnose_openvpn_failure: Callable[[list[str]], tuple[int, str]]
    status_callback: Callable[[str], None]
    log_vpn_line: Callable[[str, str], None]
    log_routing_line: Callable[[str, str], None]
    print_line: Callable[[str], None]
    sleep: Callable[[float], None]
    _openvpn_runtime_facade: OpenVPNRuntimeFacade | None = field(default=None, init=False)
    _policy_routing_facade: PolicyRoutingFacade | None = field(default=None, init=False)

    def openvpn_runtime_facade(self) -> OpenVPNRuntimeFacade:
        if self._openvpn_runtime_facade is None:
            self._openvpn_runtime_facade = OpenVPNRuntimeFacade(
                openvpn_cmd=self.openvpn_cmd,
                auth_file=self.auth_file,
                data_dir=self.data_dir,
                config_dir=self.config_dir,
                upstream_proxy_auth_path=self.upstream_proxy_auth_path,
                get_upstream_proxy=self.get_upstream_proxy,
                write_upstream_proxy_auth_file=self.write_upstream_proxy_auth_file,
                print_line=self.print_line,
            )
        return self._openvpn_runtime_facade

    def policy_routing_facade(self) -> PolicyRoutingFacade:
        if self._policy_routing_facade is None:
            self._policy_routing_facade = PolicyRoutingFacade(
                sleep=self.sleep,
                print_line=self.print_line,
                log_line=self.log_routing_line,
            )
        return self._policy_routing_facade

    def split_openvpn_command(self) -> list[str]:
        return self.openvpn_runtime_facade().split_command()

    def get_openvpn_version(self) -> float:
        return self.openvpn_runtime_facade().get_version()

    def openvpn_command(self, config_file: str, route_nopull: bool, dev: str | None = None) -> list[str]:
        return self.openvpn_runtime_facade().command(
            config_file,
            route_nopull,
            dev or self.default_dev(),
        )

    def stop_process(self, process: subprocess.Popen[str] | None) -> None:
        self.openvpn_runtime_facade().stop_process(process)

    def kill_existing_openvpn_processes(self) -> None:
        self.openvpn_runtime_facade().kill_existing_processes()

    def run_openvpn_until_ready(
        self,
        config_file: str,
        *,
        keep_alive: bool,
        route_nopull: bool,
        timeout: int | None = None,
        dev: str | None = None,
    ) -> tuple[bool, str, subprocess.Popen[str] | None]:
        return self.openvpn_runtime_facade().run_until_ready(
            config_file=config_file,
            keep_alive=keep_alive,
            route_nopull=route_nopull,
            timeout=timeout if timeout is not None else self.default_timeout_seconds(),
            dev=dev or self.default_dev(),
            cwd=self.root_dir,
            diagnose_failure=self.diagnose_openvpn_failure,
            log_line=self.log_vpn_line,
            status_callback=self.status_callback,
            print_line=self.print_line,
        )

    def setup_policy_routing(self, interface: str | None = None, table: str | None = None) -> None:
        self.policy_routing_facade().setup(
            interface or self.default_dev(),
            table or self.policy_table(),
        )

    def cleanup_policy_routing(self, table: str | None = None) -> None:
        self.policy_routing_facade().cleanup(table or self.policy_table())
