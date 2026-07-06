from __future__ import annotations

from aimilivpn.system.manager_web import ManagerWebRuntime
from aimilivpn.system.manager_wiring_factory_common import build_runtime
from aimilivpn.system.manager_wiring_web_types import WebManagerRuntimeWiring


def build_web_runtime(wiring: WebManagerRuntimeWiring) -> ManagerWebRuntime:
    return build_runtime(ManagerWebRuntime, wiring)
