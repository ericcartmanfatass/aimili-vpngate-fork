from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping

from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository
from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.system.runtime_paths import RuntimePaths


@dataclass(frozen=True)
class ManagerRepositories:
    node_repository: NodeRepository
    region_repository: RegionRepository
    quality_repository: QualityRepository


@dataclass(frozen=True)
class ManagerSharedState:
    lock: Any
    maintenance_lock: Any
    mutable_state: ManagerMutableState
    active_sessions: MutableMapping[str, float]


@dataclass(frozen=True)
class ManagerUiEndpoints:
    ui_host: str
    ui_port: int
    local_proxy_port: int


@dataclass(frozen=True)
class RepositoryRuntimeWiring:
    node_repository: NodeRepository
    region_repository: RegionRepository
    country_translations: Mapping[str, str]


@dataclass(frozen=True)
class QualityRuntimeWiring:
    root_dir: Path
    quality_repository: QualityRepository
    region_repository: RegionRepository
    region_target_id: Callable[[str], str]
    read_nodes: Callable[[], list[dict[str, Any]]]
    node_allowed: Callable[[dict[str, Any]], bool]
    bounded_int: Callable[[Any, int, int | None, int | None], int]
    test_multiple_nodes: Callable[[list[str]], list[dict[str, Any]]]


@dataclass(frozen=True)
class UiRuntimeWiring:
    data_dir: Callable[[], Path]
    lock: Any
    ui_host: Callable[[], str]
    ui_port: Callable[[], int]
    proxy_port: Callable[[], int]
    bounded_int: Callable[[Any, int, int, int], int]


@dataclass(frozen=True)
class RuntimeStateWiring:
    state_file: Callable[[], Path]
    lock: Any
    mutable_state: ManagerMutableState
    load_ui_config: Callable[[], dict[str, Any]]
    api_url: Callable[[], str]
    instance_id: Callable[[], str]
    tun_dev: Callable[[], str]
    policy_table: Callable[[], str]
    allowed_countries: Callable[[], Iterable[str]]
    target_valid_nodes: Callable[[], int]
    fetch_interval_seconds: Callable[[], int]
    check_interval_seconds: Callable[[], int]
    local_proxy_host: Callable[[], str]
    local_proxy_port: Callable[[], int]


@dataclass(frozen=True)
class RuntimeFilesWiring:
    paths: Callable[[], RuntimePaths]
    auth_user: Callable[[], str]
    auth_pass: Callable[[], str]
    get_upstream_proxy_auth: Callable[[], tuple[str | None, str | None]]
    print_line: Callable[[str], None]
