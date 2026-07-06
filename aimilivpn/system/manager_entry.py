from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from aimilivpn.system.service_runtime import VpnGateServiceRuntime
from aimilivpn.web.server import WebRequestHandler, WebServerRuntime


@dataclass
class ManagerEntryRuntime:
    service_runtime_factory: Callable[[], VpnGateServiceRuntime]
    web_server_runtime: Callable[[], WebServerRuntime]
    _handler_class: type[WebRequestHandler] | None = field(default=None, init=False)

    def service_runtime(self) -> VpnGateServiceRuntime:
        return self.service_runtime_factory()

    def handler_class(self) -> type[WebRequestHandler]:
        if self._handler_class is None:
            web_server_runtime = self.web_server_runtime

            class Handler(WebRequestHandler):
                @property
                def runtime(self) -> WebServerRuntime:
                    return web_server_runtime()

            self._handler_class = Handler
        return self._handler_class

    def main(self) -> None:
        self.service_runtime().main()
