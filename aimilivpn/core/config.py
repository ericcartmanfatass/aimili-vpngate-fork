from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aimilivpn.web.proxy_trust import DEFAULT_TRUSTED_PROXY_ADDRESSES, parse_trusted_proxy_addresses


def env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.environ.get(name)
    raw_text = raw.strip() if raw is not None else ""
    try:
        value = int(raw_text) if raw_text else default
    except (TypeError, ValueError):
        return default
    if min_value is not None and value < min_value:
        return default
    if max_value is not None and value > max_value:
        return default
    return value


def env_text(name: str, default: str) -> str:
    value = (os.environ.get(name) or "").strip()
    return value or default


def env_bool(name: str, default: bool = False) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    config_dir: Path
    nodes_file: Path
    state_file: Path
    auth_file: Path
    local_proxy_host: str
    local_proxy_port: int
    ui_host: str
    ui_port: int
    openvpn_cmd: str
    tun_dev: str
    policy_table: str
    allowed_countries: set[str]
    allow_insecure_fetch: bool
    trust_proxy_headers: bool = False
    trusted_proxy_addresses: tuple[str, ...] = DEFAULT_TRUSTED_PROXY_ADDRESSES
    api_url: str = "https://www.vpngate.net/api/iphone/"
    max_scan_rows: int = 300
    scamalytics_username: str = ""
    scamalytics_api_key: str = ""
    scamalytics_timeout_seconds: int = 8
    scamalytics_cache_ttl_seconds: int = 86400
    scamalytics_rate_limit_per_minute: int = 30
    scamalytics_api_url: str = "https://api11.scamalytics.com/{username}/"
    scamalytics_enabled: bool = True

    @property
    def scamalytics_configured(self) -> bool:
        return bool(self.scamalytics_enabled and self.scamalytics_username and self.scamalytics_api_key)

    @property
    def blacklist_file(self) -> Path:
        return self.data_dir / "blacklist.json"

    @property
    def regions_file(self) -> Path:
        return self.data_dir / "regions.json"

    @property
    def quality_results_file(self) -> Path:
        return self.data_dir / "quality_results.json"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"


def load_config(root_dir: Path | None = None) -> AppConfig:
    root = (root_dir or Path.cwd()).resolve()
    data_dir_env = (os.environ.get("VPNGATE_DATA_DIR") or "").strip()
    data_dir = Path(data_dir_env).resolve() if data_dir_env else root / "vpngate_data"
    allowed_countries = {
        item.strip().upper()
        for item in os.environ.get("ALLOWED_COUNTRIES", "").split(",")
        if item.strip()
    }
    return AppConfig(
        data_dir=data_dir,
        config_dir=data_dir / "configs",
        nodes_file=data_dir / "nodes.json",
        state_file=data_dir / "state.json",
        auth_file=data_dir / "vpngate_auth.txt",
        local_proxy_host=env_text("LOCAL_PROXY_HOST", "127.0.0.1"),
        local_proxy_port=env_int("LOCAL_PROXY_PORT", 7928, 1, 65535),
        ui_host=env_text("UI_HOST", "127.0.0.1"),
        ui_port=env_int("UI_PORT", 8787, 1, 65535),
        trust_proxy_headers=env_bool("AIMILIVPN_TRUST_PROXY_HEADERS"),
        trusted_proxy_addresses=parse_trusted_proxy_addresses(
            os.environ.get("AIMILIVPN_TRUSTED_PROXY_ADDRESSES")
        ),
        openvpn_cmd=env_text("OPENVPN_CMD", "openvpn"),
        tun_dev=os.environ.get("TUN_DEV", "tun0").strip() or "tun0",
        policy_table=os.environ.get("POLICY_TABLE", "100").strip() or "100",
        allowed_countries=allowed_countries,
        allow_insecure_fetch=env_bool("ALLOW_INSECURE_FETCH"),
        api_url=env_text("VPNGATE_API_URL", "https://www.vpngate.net/api/iphone/"),
        max_scan_rows=env_int("MAX_SCAN_ROWS", 300, 1),
        scamalytics_username=os.environ.get("SCAMALYTICS_USERNAME", "").strip(),
        scamalytics_api_key=os.environ.get("SCAMALYTICS_API_KEY", "").strip(),
        scamalytics_timeout_seconds=env_int("SCAMALYTICS_TIMEOUT_SECONDS", 8, 1),
        scamalytics_cache_ttl_seconds=env_int("SCAMALYTICS_CACHE_TTL_SECONDS", 86400, 60),
        scamalytics_rate_limit_per_minute=env_int("SCAMALYTICS_RATE_LIMIT_PER_MINUTE", 30, 1),
        scamalytics_api_url=env_text("SCAMALYTICS_API_URL", "https://api11.scamalytics.com/{username}/"),
        scamalytics_enabled=env_bool("SCAMALYTICS_ENABLED", True),
    )
