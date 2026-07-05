from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default
    if min_value is not None and value < min_value:
        return default
    if max_value is not None and value > max_value:
        return default
    return value


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
    api_url: str = "https://www.vpngate.net/api/iphone/"
    max_scan_rows: int = 300
    scamalytics_username: str = ""
    scamalytics_api_key: str = ""
    scamalytics_timeout_seconds: int = 8
    scamalytics_cache_ttl_seconds: int = 86400
    scamalytics_rate_limit_per_minute: int = 30
    scamalytics_api_url: str = "https://api11.scamalytics.com/{username}/"

    @property
    def scamalytics_configured(self) -> bool:
        return bool(self.scamalytics_username and self.scamalytics_api_key)


def load_config(root_dir: Path | None = None) -> AppConfig:
    root = root_dir or Path.cwd()
    data_dir = Path(os.environ["VPNGATE_DATA_DIR"]).resolve() if os.environ.get("VPNGATE_DATA_DIR") else root / "vpngate_data"
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
        local_proxy_host=os.environ.get("LOCAL_PROXY_HOST", "127.0.0.1"),
        local_proxy_port=env_int("LOCAL_PROXY_PORT", 7928, 1, 65535),
        ui_host=os.environ.get("UI_HOST", "::"),
        ui_port=env_int("UI_PORT", 8787, 1, 65535),
        openvpn_cmd=os.environ.get("OPENVPN_CMD", "openvpn"),
        tun_dev=os.environ.get("TUN_DEV", "tun0").strip() or "tun0",
        policy_table=os.environ.get("POLICY_TABLE", "100").strip() or "100",
        allowed_countries=allowed_countries,
        allow_insecure_fetch=os.environ.get("ALLOW_INSECURE_FETCH", "").strip().lower() in {"1", "true", "yes", "on"},
        api_url=os.environ.get("VPNGATE_API_URL", "https://www.vpngate.net/api/iphone/"),
        max_scan_rows=env_int("MAX_SCAN_ROWS", 300, 1),
        scamalytics_username=os.environ.get("SCAMALYTICS_USERNAME", "").strip(),
        scamalytics_api_key=os.environ.get("SCAMALYTICS_API_KEY", "").strip(),
        scamalytics_timeout_seconds=env_int("SCAMALYTICS_TIMEOUT_SECONDS", 8, 1),
        scamalytics_cache_ttl_seconds=env_int("SCAMALYTICS_CACHE_TTL_SECONDS", 86400, 60),
        scamalytics_rate_limit_per_minute=env_int("SCAMALYTICS_RATE_LIMIT_PER_MINUTE", 30, 1),
        scamalytics_api_url=os.environ.get("SCAMALYTICS_API_URL", "https://api11.scamalytics.com/{username}/").strip(),
    )
