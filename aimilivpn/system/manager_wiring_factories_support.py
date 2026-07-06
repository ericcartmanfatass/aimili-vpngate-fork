from __future__ import annotations

from aimilivpn.system.manager_fetch import ManagerFetchRuntime
from aimilivpn.system.manager_logging import ManagerJsonLogRuntime
from aimilivpn.system.manager_node_view import ManagerNodeViewRuntime
from aimilivpn.system.manager_proxy_health import ManagerProxyHealthRuntime
from aimilivpn.system.manager_threads import ManagerThreadRuntime
from aimilivpn.system.manager_wiring_factory_common import build_runtime
from aimilivpn.system.manager_wiring_support_types import (
    FetchRuntimeWiring,
    JsonLogRuntimeWiring,
    NodeViewRuntimeWiring,
    ProxyHealthRuntimeWiring,
    ThreadRuntimeWiring,
)


def build_fetch_runtime(wiring: FetchRuntimeWiring) -> ManagerFetchRuntime:
    return build_runtime(ManagerFetchRuntime, wiring)


def build_thread_runtime(wiring: ThreadRuntimeWiring) -> ManagerThreadRuntime:
    return build_runtime(ManagerThreadRuntime, wiring)


def build_node_view_runtime(wiring: NodeViewRuntimeWiring) -> ManagerNodeViewRuntime:
    return build_runtime(ManagerNodeViewRuntime, wiring)


def build_proxy_health_runtime(wiring: ProxyHealthRuntimeWiring) -> ManagerProxyHealthRuntime:
    return build_runtime(ManagerProxyHealthRuntime, wiring)


def build_json_log_runtime(wiring: JsonLogRuntimeWiring) -> ManagerJsonLogRuntime:
    return build_runtime(ManagerJsonLogRuntime, wiring)
