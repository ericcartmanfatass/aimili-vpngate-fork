from __future__ import annotations

import threading
from pathlib import Path

from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository, SettingsRepository, build_store
from aimilivpn.system.manager_auth import ManagerAuthRuntime
from aimilivpn.system.manager_quality import ManagerQualityRuntime
from aimilivpn.system.manager_repository import ManagerRepositoryRuntime
from aimilivpn.system.manager_runtime_files import ManagerRuntimeFiles
from aimilivpn.system.manager_runtime_state import ManagerRuntimeState
from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.system.manager_ui import ManagerUiRuntime
from aimilivpn.system.manager_wiring_factory_common import build_runtime
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
from aimilivpn.system.runtime_paths import RuntimePaths


def build_repositories(
    paths: RuntimePaths,
    *,
    storage_backend: str = "json",
    sqlite_db_path: Path | None = None,
) -> ManagerRepositories:
    store = None
    if (storage_backend or "json").strip().lower() != "json":
        store = build_store(storage_backend, sqlite_db_path=sqlite_db_path)
    store_kwargs = {"store": store} if store is not None else {}
    return ManagerRepositories(
        node_repository=NodeRepository(paths.nodes_file, **store_kwargs),
        region_repository=RegionRepository(paths.regions_file, **store_kwargs),
        quality_repository=QualityRepository(paths.quality_results_file, **store_kwargs),
        settings_repository=SettingsRepository(paths.settings_file, **store_kwargs),
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


def build_repository_runtime(wiring: RepositoryRuntimeWiring) -> ManagerRepositoryRuntime:
    return build_runtime(ManagerRepositoryRuntime, wiring)


def build_quality_runtime(wiring: QualityRuntimeWiring) -> ManagerQualityRuntime:
    return build_runtime(ManagerQualityRuntime, wiring)


def build_ui_runtime(wiring: UiRuntimeWiring) -> ManagerUiRuntime:
    return build_runtime(ManagerUiRuntime, wiring)


def build_runtime_state(wiring: RuntimeStateWiring) -> ManagerRuntimeState:
    return build_runtime(ManagerRuntimeState, wiring)


def build_runtime_files(wiring: RuntimeFilesWiring) -> ManagerRuntimeFiles:
    return build_runtime(ManagerRuntimeFiles, wiring)
