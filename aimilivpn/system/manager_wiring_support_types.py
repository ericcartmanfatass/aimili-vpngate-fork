from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class FetchRuntimeWiring:
    api_url: str
    config_dir: Path
    max_scan_rows: int
    allowed_countries: set[str]
    allow_insecure_fetch: bool
    blacklist_file: Path
    lock: Any
    invalid_backoff_seconds: int
    read_nodes: Callable[[], list[dict[str, Any]]]
    set_state: Callable[..., None]
    log_line: Callable[[str, str], None]
    diagnose_api_failure: Callable[[str], tuple[Any, str]]
    get_upstream_proxy: Callable[[], tuple[str, str, int]]
    get_upstream_proxy_auth: Callable[[], tuple[str | None, str | None]]
    country_translations: dict[str, str]
    safe_name: Callable[[str], str]
    now: Callable[[], float]


@dataclass(frozen=True)
class ThreadRuntimeWiring:
    lock: Any
    maintenance_lock: Any
    maintain_valid_nodes: Callable[[bool], Any]
    on_thread_error: Callable[[str, BaseException], None]


@dataclass(frozen=True)
class NodeViewRuntimeWiring:
    allowed_countries: Callable[[], Iterable[str]]
    active_node_id: Callable[[], str]
    parse_int: Callable[[Any], int]


@dataclass(frozen=True)
class ProxyHealthRuntimeWiring:
    proxy_host: Callable[[], str]
    proxy_port: Callable[[], int]
    tun_dev: Callable[[], str]
    is_linux: Callable[[], bool]
    get_proxy_credentials: Callable[[], tuple[str | None, str | None]]
    diagnose_local_obstructions: Callable[[int, str], tuple[bool, str] | None]


@dataclass(frozen=True)
class JsonLogRuntimeWiring:
    data_dir: Path
    lock: object
    redact_message: Callable[[str], str]
