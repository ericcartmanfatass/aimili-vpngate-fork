from __future__ import annotations

from aimilivpn.system.manager_connection import ManagerConnectionRuntime
from aimilivpn.system.manager_monitoring import ManagerMonitoringRuntime
from aimilivpn.system.manager_wiring_connection_types import (
    ConnectionRuntimeWiring,
    MonitoringRuntimeWiring,
)
from aimilivpn.system.manager_wiring_factory_common import build_runtime


def build_connection_runtime(wiring: ConnectionRuntimeWiring) -> ManagerConnectionRuntime:
    return build_runtime(ManagerConnectionRuntime, wiring)


def build_monitoring_runtime(wiring: MonitoringRuntimeWiring) -> ManagerMonitoringRuntime:
    return build_runtime(ManagerMonitoringRuntime, wiring)
