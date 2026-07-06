from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from aimilivpn.core import openvpn as openvpn_core
from aimilivpn.system.runtime_paths import RuntimePaths, ensure_runtime_dirs, write_upstream_proxy_auth_file


@dataclass
class ManagerRuntimeFiles:
    paths: Callable[[], RuntimePaths]
    auth_user: Callable[[], str]
    auth_pass: Callable[[], str]
    get_upstream_proxy_auth: Callable[[], tuple[str | None, str | None]]
    print_line: Callable[[str], None]

    def ensure_dirs(self) -> None:
        ensure_runtime_dirs(self.paths(), self.auth_user(), self.auth_pass())

    def upstream_proxy_auth_file(self) -> str | None:
        return write_upstream_proxy_auth_file(
            self.paths(),
            self.get_upstream_proxy_auth,
            self.print_line,
        )

    def write_ovpn_config(self, path: Path, config_text: str) -> None:
        openvpn_core.write_ovpn_config(path, config_text)
