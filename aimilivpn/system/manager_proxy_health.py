from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aimilivpn.core import proxy as proxy_core


@dataclass
class ManagerProxyHealthRuntime:
    proxy_host: Callable[[], str]
    proxy_port: Callable[[], int]
    tun_dev: Callable[[], str]
    is_linux: Callable[[], bool]
    get_proxy_credentials: Callable[[], tuple[str | None, str | None]]
    diagnose_local_obstructions: Callable[[int, str], tuple[bool, str] | None]

    def check_proxy_health(self) -> dict[str, Any]:
        return proxy_core.check_proxy_health(
            proxy_host=self.proxy_host(),
            proxy_port=self.proxy_port(),
            tun_dev=self.tun_dev(),
            is_linux=self.is_linux(),
            get_proxy_credentials=self.get_proxy_credentials,
            diagnose_local_obstructions=self.diagnose_local_obstructions,
        )
