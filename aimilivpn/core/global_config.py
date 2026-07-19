from __future__ import annotations

"""Versioned v1.0.3 global configuration.

The instance runtime still accepts its historical environment variables.  This
module is the durable, user-facing configuration contract used by Console and
the global scheduler.  Secrets deliberately live in a separate private file.
"""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


GLOBAL_CONFIG_SCHEMA_VERSION = 1
APP_VERSION = "1.0.3"
DEFAULT_VPNGATE_API_URL = "https://www.vpngate.net/api/iphone/"
DEFAULT_SCAMALYTICS_API_URL = "https://api11.scamalytics.com/{username}/"
DEFAULT_VPNGATE_RETRY_BACKOFF = (300, 900, 1800, 3600)
DEFAULT_INSTANCE_RETRY_BACKOFF = (60, 300, 900, 1800)

_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_SENSITIVE_NAMES = {
    "api_key",
    "password",
    "password_hash",
    "proxy_password",
    "session",
    "session_token",
    "token",
    "secret",
    "secret_path",
}


class GlobalConfigError(ValueError):
    """Raised when a global configuration payload is invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "GLOBAL_CONFIG_INVALID",
        field: str = "",
        technical_message: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = code
        self.details = {
            **({"field": field} if field else {}),
            **({"technical_message": technical_message} if technical_message else {}),
        }


@dataclass(frozen=True)
class GlobalSettings:
    vpn_gate_enabled: bool = True
    vpn_gate_schedule_time: str = "03:30"
    vpn_gate_timezone: str = "local"
    vpn_gate_api_url: str = DEFAULT_VPNGATE_API_URL
    old_snapshot_grace_hours: int = 48
    vpn_gate_retry_backoff_seconds: tuple[int, ...] = DEFAULT_VPNGATE_RETRY_BACKOFF
    scamalytics_enabled: bool = False
    scamalytics_username: str = ""
    scamalytics_api_url: str = DEFAULT_SCAMALYTICS_API_URL
    scamalytics_timeout_seconds: int = 8
    scamalytics_rate_limit_per_minute: int = 30
    scamalytics_daily_quota: int = 1000
    scamalytics_cache_ttl_days: int = 7
    scamalytics_risk_threshold: int = 70
    instance_retry_backoff_seconds: tuple[int, ...] = DEFAULT_INSTANCE_RETRY_BACKOFF
    connection_candidate_limit: int = 3
    json_log_retention_days: int = 7
    text_log_max_bytes: int = 10 * 1024 * 1024
    text_log_backup_count: int = 7

    @property
    def scamalytics_cache_ttl_seconds(self) -> int:
        return self.scamalytics_cache_ttl_days * int(timedelta(days=1).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GLOBAL_CONFIG_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "vpn_gate_enabled": self.vpn_gate_enabled,
            "vpn_gate_schedule_time": self.vpn_gate_schedule_time,
            "vpn_gate_timezone": self.vpn_gate_timezone,
            "vpn_gate_api_url": self.vpn_gate_api_url,
            "old_snapshot_grace_hours": self.old_snapshot_grace_hours,
            "vpn_gate_retry_backoff_seconds": list(self.vpn_gate_retry_backoff_seconds),
            "scamalytics_enabled": self.scamalytics_enabled,
            "scamalytics_username": self.scamalytics_username,
            "scamalytics_api_url": self.scamalytics_api_url,
            "scamalytics_timeout_seconds": self.scamalytics_timeout_seconds,
            "scamalytics_rate_limit_per_minute": self.scamalytics_rate_limit_per_minute,
            "scamalytics_daily_quota": self.scamalytics_daily_quota,
            "scamalytics_cache_ttl_days": self.scamalytics_cache_ttl_days,
            "scamalytics_risk_threshold": self.scamalytics_risk_threshold,
            "instance_retry_backoff_seconds": list(self.instance_retry_backoff_seconds),
            "connection_candidate_limit": self.connection_candidate_limit,
            "json_log_retention_days": self.json_log_retention_days,
            "text_log_max_bytes": self.text_log_max_bytes,
            "text_log_backup_count": self.text_log_backup_count,
        }


def _atomic_write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        os.close(fd)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        tmp.unlink(missing_ok=True)


def global_config_paths(config_dir: Path) -> tuple[Path, Path]:
    root = Path(config_dir)
    return root / "global_settings.json", root / "global_secrets.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _validate_url(name: str, value: Any, default: str) -> str:
    text = str(value or default).strip()
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GlobalConfigError(
            f"{name} 必须是 HTTP 或 HTTPS 地址。",
            code="GLOBAL_SETTING_INVALID_URL",
            field=name,
            technical_message="URL scheme or host is invalid",
        )
    if parsed.username or parsed.password or parsed.query:
        raise GlobalConfigError(
            f"{name} 不能包含用户名、密码或查询参数。",
            code="GLOBAL_SETTING_UNSAFE_URL",
            field=name,
            technical_message="URL contains credentials or query parameters",
        )
    return text


def _bounded_int(name: str, value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if not minimum <= parsed <= maximum:
        raise GlobalConfigError(
            f"{name} 必须在 {minimum} 到 {maximum} 之间。",
            code="GLOBAL_SETTING_OUT_OF_RANGE",
            field=name,
            technical_message=f"expected range {minimum}..{maximum}",
        )
    return parsed


def _bool(name: str, value: Any, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise GlobalConfigError(
            f"{name} 必须是布尔值。",
            code="GLOBAL_SETTING_INVALID_TYPE",
            field=name,
            technical_message="expected boolean",
        )
    return value


def _backoff(name: str, value: Any, default: tuple[int, ...]) -> tuple[int, ...]:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or not value or len(value) > 8:
        raise GlobalConfigError(
            f"{name} 必须包含 1 到 8 个正整数秒数。",
            code="GLOBAL_SETTING_INVALID_BACKOFF",
            field=name,
            technical_message="expected one to eight positive seconds",
        )
    parsed = tuple(_bounded_int(name, item, 1, 1, 86400 * 7) for item in value)
    if any(left > right for left, right in zip(parsed, parsed[1:])):
        raise GlobalConfigError(
            f"{name} 必须按从小到大排列。",
            code="GLOBAL_SETTING_INVALID_BACKOFF",
            field=name,
            technical_message="backoff values must be sorted ascending",
        )
    return parsed


def normalize_global_settings(payload: Mapping[str, Any] | None) -> GlobalSettings:
    raw = dict(payload or {})
    schedule = str(raw.get("vpn_gate_schedule_time", "03:30")).strip()
    if not _TIME_PATTERN.fullmatch(schedule):
        raise GlobalConfigError(
            "VPNGate 每日更新时间必须使用 HH:MM 格式。",
            code="GLOBAL_SETTING_INVALID_TIME",
            field="vpn_gate_schedule_time",
            technical_message="expected HH:MM",
        )
    timezone_name = str(raw.get("vpn_gate_timezone", "local")).strip() or "local"
    if timezone_name != "local":
        if timezone_name.upper() not in {"UTC", "GMT", "ETC/UTC"}:
            try:
                ZoneInfo(timezone_name)
            except Exception as exc:
                raise GlobalConfigError(
                    "VPNGate 时区无效或当前系统不支持。",
                    code="GLOBAL_SETTING_INVALID_TIMEZONE",
                    field="vpn_gate_timezone",
                    technical_message="timezone is not supported",
                ) from exc
    return GlobalSettings(
        vpn_gate_enabled=_bool("vpn_gate_enabled", raw.get("vpn_gate_enabled"), True),
        vpn_gate_schedule_time=schedule,
        vpn_gate_timezone=timezone_name,
        vpn_gate_api_url=_validate_url("vpn_gate_api_url", raw.get("vpn_gate_api_url"), DEFAULT_VPNGATE_API_URL),
        old_snapshot_grace_hours=_bounded_int("old_snapshot_grace_hours", raw.get("old_snapshot_grace_hours"), 48, 1, 168),
        vpn_gate_retry_backoff_seconds=_backoff(
            "vpn_gate_retry_backoff_seconds", raw.get("vpn_gate_retry_backoff_seconds"), DEFAULT_VPNGATE_RETRY_BACKOFF
        ),
        scamalytics_enabled=_bool("scamalytics_enabled", raw.get("scamalytics_enabled"), False),
        scamalytics_username=str(raw.get("scamalytics_username", "") or "").strip()[:128],
        scamalytics_api_url=_validate_url(
            "scamalytics_api_url", raw.get("scamalytics_api_url"), DEFAULT_SCAMALYTICS_API_URL
        ),
        scamalytics_timeout_seconds=_bounded_int("scamalytics_timeout_seconds", raw.get("scamalytics_timeout_seconds"), 8, 1, 120),
        scamalytics_rate_limit_per_minute=_bounded_int(
            "scamalytics_rate_limit_per_minute", raw.get("scamalytics_rate_limit_per_minute"), 30, 1, 10000
        ),
        scamalytics_daily_quota=_bounded_int(
            "scamalytics_daily_quota", raw.get("scamalytics_daily_quota"), 1000, 1, 1000000
        ),
        scamalytics_cache_ttl_days=_bounded_int("scamalytics_cache_ttl_days", raw.get("scamalytics_cache_ttl_days"), 7, 1, 90),
        scamalytics_risk_threshold=_bounded_int("scamalytics_risk_threshold", raw.get("scamalytics_risk_threshold"), 70, 0, 100),
        instance_retry_backoff_seconds=_backoff(
            "instance_retry_backoff_seconds", raw.get("instance_retry_backoff_seconds"), DEFAULT_INSTANCE_RETRY_BACKOFF
        ),
        connection_candidate_limit=_bounded_int("connection_candidate_limit", raw.get("connection_candidate_limit"), 3, 1, 10),
        json_log_retention_days=_bounded_int("json_log_retention_days", raw.get("json_log_retention_days"), 7, 1, 90),
        text_log_max_bytes=_bounded_int("text_log_max_bytes", raw.get("text_log_max_bytes"), 10 * 1024 * 1024, 1024, 1024 * 1024 * 1024),
        text_log_backup_count=_bounded_int("text_log_backup_count", raw.get("text_log_backup_count"), 7, 1, 32),
    )


def load_global_settings(config_dir: Path) -> GlobalSettings:
    settings_path, _ = global_config_paths(config_dir)
    return normalize_global_settings(_read_json(settings_path))


def load_global_secrets(config_dir: Path) -> dict[str, str]:
    _, secrets_path = global_config_paths(config_dir)
    payload = _read_json(secrets_path)
    return {
        "scamalytics_username": str(payload.get("scamalytics_username") or "").strip(),
        "scamalytics_api_key": str(payload.get("scamalytics_api_key") or "").strip(),
    }


def save_global_settings(
    config_dir: Path,
    payload: Mapping[str, Any],
    *,
    scamalytics_api_key: str | None = None,
) -> GlobalSettings:
    settings_path, secrets_path = global_config_paths(config_dir)
    current = load_global_settings(config_dir)
    merged = current.to_dict()
    for key, value in payload.items():
        if key not in merged or key in {"schema_version", "app_version"}:
            continue
        merged[key] = value
    settings = normalize_global_settings(merged)
    _atomic_write(settings_path, settings.to_dict())
    secrets = load_global_secrets(config_dir)
    if "scamalytics_username" in payload:
        secrets["scamalytics_username"] = settings.scamalytics_username
    if scamalytics_api_key is not None:
        secrets["scamalytics_api_key"] = str(scamalytics_api_key).strip()
    if secrets["scamalytics_username"] or secrets["scamalytics_api_key"]:
        _atomic_write(secrets_path, secrets)
    elif secrets_path.exists():
        secrets_path.unlink(missing_ok=True)
    return settings


def public_global_settings(config_dir: Path) -> dict[str, Any]:
    settings = load_global_settings(config_dir)
    secrets = load_global_secrets(config_dir)
    data = settings.to_dict()
    data["scamalytics_api_key_configured"] = bool(secrets.get("scamalytics_api_key"))
    data["scamalytics_api_key_masked"] = "********" if secrets.get("scamalytics_api_key") else ""
    return data


def global_settings_for_runtime(config_dir: Path) -> dict[str, Any]:
    settings = load_global_settings(config_dir)
    secrets = load_global_secrets(config_dir)
    data = settings.to_dict()
    data.update(secrets)
    return data


def resolve_global_config_dir(root_dir: Path | None = None) -> Path:
    configured = (os.environ.get("AIMILIVPN_CONFIG_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (root_dir or Path.cwd()).resolve() / "config"
