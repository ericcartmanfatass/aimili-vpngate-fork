from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import time

from aimilivpn.system.blacklist_store import BlacklistStore
from aimilivpn.system.vpngate_fetch import VpnGateFetchFacade
from aimilivpn.core.storage import BlacklistRepository
from aimilivpn.core.global_nodes import read_global_nodes


@dataclass
class ManagerFetchRuntime:
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
    now: Callable[[], float] = time.time
    blacklist_repository: BlacklistRepository | None = None
    global_nodes_file: Path | None = None
    get_state: Callable[[], dict[str, Any]] | None = None
    global_retry_backoff_seconds: tuple[int, ...] = (60, 300, 900, 1800)

    def blacklist_store(self) -> BlacklistStore:
        kwargs: dict[str, Any] = {
            "path": self.blacklist_file,
            "lock": self.lock,
            "backoff_seconds": self.invalid_backoff_seconds,
            "now": self.now,
        }
        if self.blacklist_repository is not None:
            kwargs["repository"] = self.blacklist_repository
        return BlacklistStore(
            **kwargs,
        )

    def load_blacklist(self) -> dict[str, dict[str, Any]]:
        return self.blacklist_store().load()

    def mark_blacklisted(self, node: dict[str, Any], message: str) -> None:
        self.blacklist_store().mark(node, message)

    def cached_nodes(self) -> list[dict[str, Any]]:
        return self.read_nodes()

    def facade(self) -> VpnGateFetchFacade:
        return VpnGateFetchFacade(
            api_url=self.api_url,
            config_dir=self.config_dir,
            max_scan_rows=self.max_scan_rows,
            allowed_countries=self.allowed_countries,
            allow_insecure_fetch=self.allow_insecure_fetch,
            load_blacklist=self.load_blacklist,
            cached_nodes=self.cached_nodes,
            set_state=self.set_state,
            log_line=self.log_line,
            diagnose_api_failure=self.diagnose_api_failure,
            get_upstream_proxy=self.get_upstream_proxy,
            get_upstream_proxy_auth=self.get_upstream_proxy_auth,
            country_translations=self.country_translations,
            safe_name=self.safe_name,
            now=self.now,
        )

    def fetch_api_text_via_proxy(
        self,
        url: str,
        proxy_type: str,
        proxy_host: str,
        proxy_port: int,
        use_ssl_verify: bool = True,
    ) -> str:
        return self.facade().fetch_api_text_via_proxy(
            url,
            proxy_type,
            proxy_host,
            proxy_port,
            use_ssl_verify,
        )

    def fetch_api_text(self, url: str | None = None, use_ssl_verify: bool = True) -> str:
        return self.facade().fetch_api_text(url, use_ssl_verify)

    def fetch_candidates(self) -> list[dict[str, Any]]:
        if self.global_nodes_file is not None:
            return self._fetch_global_candidates_with_backoff()
        if self.global_nodes_file is not None and self.global_nodes_file.exists():
            candidates = self._read_global_candidates()
            self.set_state(
                last_fetch_at=self.now(),
                last_fetch_status="ok" if candidates else "empty",
                last_fetch_message=f"读取全局节点快照，共 {len(candidates)} 个候选节点",
            )
            self.log_line("INFO", f"已读取全局 VPNGate 节点快照，共 {len(candidates)} 个候选节点")
            return candidates
        return self.facade().fetch_candidates()

    def _fetch_global_candidates_with_backoff(self) -> list[dict[str, Any]]:
        now = self.now()
        state = self.get_state() if self.get_state is not None else {}
        retry_at = _as_float(state.get("global_next_retry_at"), 0.0)
        if retry_at > now:
            self.set_state(
                last_fetch_at=now,
                last_fetch_status="backoff",
                last_fetch_message=f"全局节点快照暂无可用节点，将在 {retry_at:.0f} 后重试",
            )
            return []

        candidates = self._read_global_candidates() if self.global_nodes_file.exists() else []
        if candidates:
            self.set_state(
                last_fetch_at=now,
                last_fetch_status="ok",
                global_fetch_failure_count=0,
                global_retry_level=0,
                global_next_retry_at=0,
                last_fetch_message=f"读取全局节点快照，共 {len(candidates)} 个候选节点",
            )
        else:
            failures = int(state.get("global_fetch_failure_count") or 0) + 1
            retry_index = min(failures - 1, len(self.global_retry_backoff_seconds) - 1)
            next_retry_at = now + self.global_retry_backoff_seconds[retry_index]
            self.set_state(
                last_fetch_at=now,
                last_fetch_status="empty",
                global_fetch_failure_count=failures,
                global_retry_level=retry_index + 1,
                global_next_retry_at=next_retry_at,
                last_fetch_message=f"全局节点快照暂无可用节点，将在 {next_retry_at:.0f} 后重试",
            )
        self.set_state(global_snapshot_source=str(self.global_nodes_file))
        self.log_line("INFO", f"读取全局 VPNGate 节点快照，共 {len(candidates)} 个候选节点")
        return candidates

    def _read_global_candidates(self) -> list[dict[str, Any]]:
        blacklist = self.load_blacklist()
        candidates: list[dict[str, Any]] = []
        seen_ips: set[str] = set()
        for source in read_global_nodes(self.global_nodes_file):  # type: ignore[arg-type]
            node = dict(source)
            country = str(node.get("country_short") or node.get("country_code") or "").strip().upper()
            ip = str(node.get("server_ip") or node.get("ip") or node.get("remote_host") or "").strip()
            if self.allowed_countries and country not in self.allowed_countries:
                continue
            if not ip or ip in seen_ips or str(node.get("id") or "") in blacklist:
                continue
            config_file = Path(str(node.get("config_file") or ""))
            if config_file.exists():
                try:
                    node["config_text"] = config_file.read_text(encoding="utf-8")
                except OSError:
                    continue
            candidates.append(node)
            seen_ips.add(ip)
        return candidates


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
