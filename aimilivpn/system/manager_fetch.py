from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import time

from aimilivpn.system.blacklist_store import BlacklistStore
from aimilivpn.system.vpngate_fetch import VpnGateFetchFacade


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

    def blacklist_store(self) -> BlacklistStore:
        return BlacklistStore(
            path=self.blacklist_file,
            lock=self.lock,
            backoff_seconds=self.invalid_backoff_seconds,
            now=self.now,
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
        return self.facade().fetch_candidates()
