from __future__ import annotations

import threading
from typing import Callable, TypeVar

from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository
from aimilivpn.system.manager_auth import ManagerAuthRuntime
from aimilivpn.system.manager_connection import ManagerConnectionRuntime
from aimilivpn.system.manager_entry import ManagerEntryRuntime
from aimilivpn.system.manager_fetch import ManagerFetchRuntime
from aimilivpn.system.manager_logging import ManagerJsonLogRuntime
from aimilivpn.system.manager_monitoring import ManagerMonitoringRuntime
from aimilivpn.system.manager_node_probe import ManagerNodeProbeRuntime
from aimilivpn.system.manager_node_view import ManagerNodeViewRuntime
from aimilivpn.system.manager_openvpn import ManagerOpenVPNRuntime
from aimilivpn.system.manager_proxy_health import ManagerProxyHealthRuntime
from aimilivpn.system.manager_quality import ManagerQualityRuntime
from aimilivpn.system.manager_repository import ManagerRepositoryRuntime
from aimilivpn.system.manager_runtime_files import ManagerRuntimeFiles
from aimilivpn.system.manager_runtime_state import ManagerRuntimeState
from aimilivpn.system.manager_service import ManagerServiceRuntime
from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.system.manager_threads import ManagerThreadRuntime
from aimilivpn.system.manager_ui import ManagerUiRuntime
from aimilivpn.system.manager_web import ManagerWebRuntime
from aimilivpn.system.manager_wiring_connection_types import (
    ConnectionRuntimeWiring,
    MonitoringRuntimeWiring,
)
from aimilivpn.system.manager_wiring_foundation_types import (
    ManagerRepositories,
    ManagerSharedState,
    ManagerUiEndpoints,
    QualityRuntimeWiring,
    RepositoryRuntimeWiring,
    RuntimeFilesWiring,
    RuntimeStateWiring,
    UiRuntimeWiring,
)
from aimilivpn.system.manager_wiring_process_types import (
    EntryRuntimeWiring,
    NodeProbeRuntimeWiring,
    OpenVPNRuntimeWiring,
    ServiceRuntimeWiring,
)
from aimilivpn.system.manager_wiring_support_types import (
    FetchRuntimeWiring,
    JsonLogRuntimeWiring,
    NodeViewRuntimeWiring,
    ProxyHealthRuntimeWiring,
    ThreadRuntimeWiring,
)
from aimilivpn.system.manager_wiring_web_types import (
    WebManagerRuntimeWiring,
)
from aimilivpn.system.runtime_paths import RuntimePaths

RuntimeT = TypeVar("RuntimeT")


def build_repositories(paths: RuntimePaths) -> ManagerRepositories:
    return ManagerRepositories(
        node_repository=NodeRepository(paths.nodes_file),
        region_repository=RegionRepository(paths.regions_file),
        quality_repository=QualityRepository(paths.quality_results_file),
    )


def build_shared_state() -> ManagerSharedState:
    mutable_state = ManagerMutableState()
    return ManagerSharedState(
        lock=threading.RLock(),
        maintenance_lock=threading.Lock(),
        mutable_state=mutable_state,
        active_sessions=mutable_state.active_sessions,
    )


def apply_saved_ui_overrides(
    ui_runtime: ManagerUiRuntime,
    ui_host: str,
    ui_port: int,
    local_proxy_port: int,
) -> ManagerUiEndpoints:
    try:
        ui_host, ui_port, local_proxy_port = ui_runtime.apply_saved_overrides()
    except Exception:
        pass
    return ManagerUiEndpoints(
        ui_host=ui_host,
        ui_port=ui_port,
        local_proxy_port=local_proxy_port,
    )


def build_auth_runtime() -> ManagerAuthRuntime:
    return ManagerAuthRuntime()


def build_entry_runtime(wiring: EntryRuntimeWiring) -> ManagerEntryRuntime:
    return _build_runtime(ManagerEntryRuntime, wiring)


def _build_runtime(runtime_cls: Callable[..., RuntimeT], wiring: object) -> RuntimeT:
    return runtime_cls(**vars(wiring))


def build_connection_runtime(wiring: ConnectionRuntimeWiring) -> ManagerConnectionRuntime:
    return _build_runtime(ManagerConnectionRuntime, wiring)


def build_repository_runtime(wiring: RepositoryRuntimeWiring) -> ManagerRepositoryRuntime:
    return _build_runtime(ManagerRepositoryRuntime, wiring)


def build_quality_runtime(wiring: QualityRuntimeWiring) -> ManagerQualityRuntime:
    return _build_runtime(ManagerQualityRuntime, wiring)


def build_fetch_runtime(wiring: FetchRuntimeWiring) -> ManagerFetchRuntime:
    return _build_runtime(ManagerFetchRuntime, wiring)


def build_ui_runtime(wiring: UiRuntimeWiring) -> ManagerUiRuntime:
    return _build_runtime(ManagerUiRuntime, wiring)


def build_runtime_state(wiring: RuntimeStateWiring) -> ManagerRuntimeState:
    return _build_runtime(ManagerRuntimeState, wiring)


def build_runtime_files(wiring: RuntimeFilesWiring) -> ManagerRuntimeFiles:
    return _build_runtime(ManagerRuntimeFiles, wiring)


def build_thread_runtime(wiring: ThreadRuntimeWiring) -> ManagerThreadRuntime:
    return _build_runtime(ManagerThreadRuntime, wiring)


def build_node_view_runtime(wiring: NodeViewRuntimeWiring) -> ManagerNodeViewRuntime:
    return _build_runtime(ManagerNodeViewRuntime, wiring)


def build_proxy_health_runtime(wiring: ProxyHealthRuntimeWiring) -> ManagerProxyHealthRuntime:
    return _build_runtime(ManagerProxyHealthRuntime, wiring)


def build_json_log_runtime(wiring: JsonLogRuntimeWiring) -> ManagerJsonLogRuntime:
    return _build_runtime(ManagerJsonLogRuntime, wiring)


def build_monitoring_runtime(wiring: MonitoringRuntimeWiring) -> ManagerMonitoringRuntime:
    return _build_runtime(ManagerMonitoringRuntime, wiring)


def build_service_runtime(wiring: ServiceRuntimeWiring) -> ManagerServiceRuntime:
    return _build_runtime(ManagerServiceRuntime, wiring)


def build_openvpn_runtime(wiring: OpenVPNRuntimeWiring) -> ManagerOpenVPNRuntime:
    return _build_runtime(ManagerOpenVPNRuntime, wiring)


def build_node_probe_runtime(wiring: NodeProbeRuntimeWiring) -> ManagerNodeProbeRuntime:
    return _build_runtime(ManagerNodeProbeRuntime, wiring)


def build_web_runtime(wiring: WebManagerRuntimeWiring) -> ManagerWebRuntime:
    return _build_runtime(ManagerWebRuntime, wiring)
