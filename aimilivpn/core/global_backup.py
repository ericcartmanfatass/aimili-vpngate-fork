from __future__ import annotations

"""Versioned, secret-free Console backup and restore primitives."""

import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .global_config import APP_VERSION, GLOBAL_CONFIG_SCHEMA_VERSION


class BackupValidationError(ValueError):
    """Raised for malformed or unsafe backup documents."""


class BackupRestoreError(RuntimeError):
    """Restore failed after reporting whether compensation succeeded."""

    def __init__(self, message: str, *, rollback_succeeded: bool, cause_type: str) -> None:
        super().__init__(message)
        self.rollback_succeeded = rollback_succeeded
        self.cause_type = cause_type
        self.error_code = "restore_failed_rolled_back" if rollback_succeeded else "restore_rollback_failed"


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:password|api[_-]?key|session|token|secret|credential|private[_-]?key|config[_-]?text|openvpn[_-]?config)",
    re.IGNORECASE,
)
_FORBIDDEN_SYSTEM_KEYS = {
    "systemd_unit",
    "service",
    "env_file",
    "data_dir",
    "tun_dev",
    "policy_table",
    "device",
    "route_table",
    "config_file",
    "proxy_host",
    "proxy_port",
    "ui_host",
    "ui_port",
    "port",
}


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def strip_sensitive(value: Any, *, reject: bool = False, path: str = "") -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                if reject:
                    raise BackupValidationError(f"敏感字段不允许出现在备份中: {path + key}")
                continue
            clean[key] = strip_sensitive(raw_value, reject=reject, path=f"{path}{key}.")
        return clean
    if isinstance(value, list):
        return [strip_sensitive(item, reject=reject, path=f"{path}[]") for item in value]
    return value


def document_checksum(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_backup_payload(
    *,
    global_settings: Mapping[str, Any],
    instances: list[Mapping[str, Any]],
    regions: list[Mapping[str, Any]] | None = None,
    backup_type: str = "config",
    nodes: list[Mapping[str, Any]] | None = None,
    quality_results: list[Mapping[str, Any]] | None = None,
    blacklist: Mapping[str, Any] | None = None,
    job_history: list[Mapping[str, Any]] | None = None,
    quality_metrics: Mapping[str, Any] | None = None,
    exported_at: str | None = None,
) -> dict[str, Any]:
    if backup_type not in {"config", "full"}:
        raise BackupValidationError("备份类型必须是 config 或 full")
    payload: dict[str, Any] = {
        "schema_version": GLOBAL_CONFIG_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "exported_at": exported_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "backup_type": backup_type,
        "global_settings": strip_sensitive(dict(global_settings)),
        "instances": strip_sensitive([dict(item) for item in instances]),
        "regions": strip_sensitive([dict(item) for item in (regions or [])]),
    }
    if backup_type == "full":
        payload.update(
            {
                "nodes": strip_sensitive([dict(item) for item in (nodes or [])]),
                "quality_results": strip_sensitive([dict(item) for item in (quality_results or [])]),
                "blacklist": strip_sensitive(dict(blacklist or {})),
                "job_history": strip_sensitive([dict(item) for item in (job_history or [])]),
                "quality_metrics": strip_sensitive(dict(quality_metrics or {})),
            }
        )
    validate_backup_payload(payload)
    return payload


def validate_backup_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BackupValidationError("备份文件必须是 JSON 对象")
    if payload.get("schema_version") != GLOBAL_CONFIG_SCHEMA_VERSION:
        raise BackupValidationError("不支持的备份 schema 版本")
    if str(payload.get("backup_type") or "") not in {"config", "full"}:
        raise BackupValidationError("备份类型无效")
    for field in ("exported_at", "app_version"):
        if not str(payload.get(field) or "").strip():
            raise BackupValidationError(f"缺少备份字段: {field}")
    if str(payload.get("app_version")) not in {"1.0.2", APP_VERSION}:
        raise BackupValidationError("备份应用版本不受支持")
    for field, expected in (("global_settings", dict), ("instances", list), ("regions", list)):
        if not isinstance(payload.get(field), expected):
            raise BackupValidationError(f"备份字段格式无效: {field}")
    if payload["backup_type"] == "full":
        for field, expected in (("nodes", list), ("quality_results", list), ("blacklist", dict), ("job_history", list)):
            if not isinstance(payload.get(field), expected):
                raise BackupValidationError(f"完整备份字段格式无效: {field}")
        if "quality_metrics" in payload and not isinstance(payload.get("quality_metrics"), dict):
            raise BackupValidationError("完整备份字段格式无效: quality_metrics")
    strip_sensitive(payload, reject=True)
    _validate_instances(payload["instances"])
    _validate_safe_system_fields(payload)
    return copy.deepcopy(payload)


def _validate_instances(instances: list[Any]) -> None:
    instance_ids: set[str] = set()
    for item in instances:
        if not isinstance(item, dict):
            raise BackupValidationError("instances 必须是对象列表")
        identifier = str(item.get("id") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", identifier):
            raise BackupValidationError("实例 ID 无效")
        if identifier in instance_ids:
            raise BackupValidationError("实例 ID 不能重复")
        instance_ids.add(identifier)
        preferences = item.get("preferences", {})
        if not isinstance(preferences, dict):
            raise BackupValidationError("实例偏好必须是对象")
        allowed = {
            "routing_mode",
            "force_country",
            "routing_ip_type",
            "connection_enabled",
            "fixed_node_id",
            "favorite_node_ids",
            "fav_fail_fallback",
        }
        if set(preferences) - allowed:
            raise BackupValidationError("实例偏好包含不支持的字段")
        if preferences.get("routing_mode", "auto") not in {"auto", "fixed_ip", "fixed_region", "favorites"}:
            raise BackupValidationError("实例路由模式无效")
        if preferences.get("routing_ip_type", "all") not in {"all", "residential", "hosting"}:
            raise BackupValidationError("实例 IP 类型无效")
        for name in ("connection_enabled", "fav_fail_fallback"):
            if name in preferences and not isinstance(preferences[name], bool):
                raise BackupValidationError(f"实例偏好字段必须是布尔值: {name}")
        favorites = preferences.get("favorite_node_ids", [])
        if not isinstance(favorites, list) or len(favorites) > 1000 or any(not isinstance(value, str) for value in favorites):
            raise BackupValidationError("收藏节点列表格式无效")


def _validate_safe_system_fields(payload: Mapping[str, Any]) -> None:
    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = str(key).lower()
                if normalized_key in _FORBIDDEN_SYSTEM_KEYS or normalized_key.endswith(("_path", "_dir")):
                    raise BackupValidationError(f"备份不允许指定系统资源: {path}{key}")
                walk(item, f"{path}{key}.")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}{index}.")
    walk(payload)


def preview_backup(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    current_clean = strip_sensitive(dict(current))
    candidate_clean = validate_backup_payload(candidate)
    details: dict[str, list[dict[str, Any]]] = {
        "added": [],
        "modified": [],
        "removed": [],
        "ignored": [],
    }
    for field in ("app_version", "exported_at"):
        details["ignored"].append(
            {
                "path": field,
                "reason": "备份元数据不会覆盖当前运行版本",
                "value": candidate_clean.get(field),
            }
        )
    _collect_differences(current_clean, candidate_clean, "", details)
    details["ignored"].append(
        {
            "path": "sensitive_credentials",
            "reason": "敏感凭据不会导出、预览或恢复",
            "fields": ["api_key", "password", "session", "token", "private_key", "openvpn_config"],
        }
    )
    changes = [
        {"action": action, **item}
        for action in ("added", "modified", "removed")
        for item in details[action]
    ]
    return {
        "changed": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        **details,
        "requires_deletion_confirmation": bool(details["removed"]),
    }


def _collect_differences(
    before: Any,
    after: Any,
    path: str,
    details: dict[str, list[dict[str, Any]]],
) -> None:
    if path in {"app_version", "exported_at"}:
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else str(key)
            if child_path in {"app_version", "exported_at"}:
                continue
            if key not in before:
                details["added"].append({"path": child_path, "after": _preview_value(after[key])})
            elif key not in after:
                details["removed"].append({"path": child_path, "before": _preview_value(before[key])})
            else:
                _collect_differences(before[key], after[key], child_path, details)
        return
    if isinstance(before, list) and isinstance(after, list):
        identity = _list_identity_key(before, after)
        if identity:
            before_by_id = {str(item[identity]): item for item in before if isinstance(item, dict) and identity in item}
            after_by_id = {str(item[identity]): item for item in after if isinstance(item, dict) and identity in item}
            for item_id in sorted(set(before_by_id) | set(after_by_id)):
                item_path = f"{path}[{item_id}]"
                if item_id not in before_by_id:
                    details["added"].append({"path": item_path, "after": _preview_value(after_by_id[item_id])})
                elif item_id not in after_by_id:
                    details["removed"].append({"path": item_path, "before": _preview_value(before_by_id[item_id])})
                else:
                    _collect_differences(before_by_id[item_id], after_by_id[item_id], item_path, details)
            return
        if before != after:
            details["modified"].append(
                {"path": path, "before": _preview_value(before), "after": _preview_value(after)}
            )
        return
    if before != after:
        details["modified"].append(
            {"path": path, "before": _preview_value(before), "after": _preview_value(after)}
        )


def _list_identity_key(before: list[Any], after: list[Any]) -> str | None:
    items = [item for item in [*before, *after] if isinstance(item, dict)]
    if not items or len(items) != len(before) + len(after):
        return None
    for key in ("id", "ip", "server_ip"):
        if all(str(item.get(key) or "").strip() for item in items):
            return key
    return None


def _preview_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return {"type": "list", "count": len(value)}
    if isinstance(value, dict):
        identifier = next(
            (str(value.get(key)) for key in ("id", "ip", "server_ip") if value.get(key)),
            "",
        )
        return {"type": "object", "identifier": identifier, "field_count": len(value)}
    return {"type": type(value).__name__}


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        os.close(fd)
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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


class BackupManager:
    def __init__(self, backup_dir: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.backup_dir = backup_dir
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def export(self, payload: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
        validated = validate_backup_payload(payload)
        stamp = self.clock().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        kind = validated["backup_type"]
        path = self.backup_dir / f"aimilivpn-v{APP_VERSION}-{kind}-{stamp}.json"
        if path.exists():
            path = self.backup_dir / f"aimilivpn-v{APP_VERSION}-{kind}-{stamp}-{os.getpid()}.json"
        _atomic_write(path, validated)
        return path, {"path": str(path), "checksum": document_checksum(validated), "payload": validated}

    def restore(
        self,
        payload: Mapping[str, Any],
        *,
        current: Mapping[str, Any],
        apply: Callable[[dict[str, Any]], None],
        rollback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        candidate = validate_backup_payload(payload)
        backup_type = "full" if candidate["backup_type"] == "full" else "config"
        current_nodes = [dict(item) for item in current.get("nodes", []) if isinstance(item, dict)]
        current_quality = current.get("quality_results", [])
        if isinstance(current_quality, dict):
            current_quality = list(current_quality.values())
        current_blacklist = current.get("blacklist", {})
        current_history = [dict(item) for item in current.get("job_history", []) if isinstance(item, dict)]
        current_quality_metrics = current.get("quality_metrics", {})
        before = build_backup_payload(
            global_settings=dict(current.get("global_settings") or {}),
            instances=[dict(item) for item in current.get("instances", []) if isinstance(item, dict)],
            regions=[dict(item) for item in current.get("regions", []) if isinstance(item, dict)],
            backup_type=backup_type,
            nodes=current_nodes if backup_type == "full" else None,
            quality_results=current_quality if backup_type == "full" else None,
            blacklist=current_blacklist if backup_type == "full" and isinstance(current_blacklist, dict) else None,
            job_history=current_history if backup_type == "full" else None,
            quality_metrics=current_quality_metrics if backup_type == "full" and isinstance(current_quality_metrics, dict) else None,
            exported_at=self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        backup_path, _ = self.export(before)
        try:
            apply(candidate)
        except Exception as exc:
            try:
                (rollback or apply)(before)
            except Exception as rollback_exc:
                raise BackupRestoreError(
                    "恢复失败，自动回滚也未能完整执行。",
                    rollback_succeeded=False,
                    cause_type=type(exc).__name__,
                ) from rollback_exc
            raise BackupRestoreError(
                "恢复失败，已自动回滚到恢复前状态。",
                rollback_succeeded=True,
                cause_type=type(exc).__name__,
            ) from exc
        return {"ok": True, "backup_before_restore": str(backup_path), "checksum": document_checksum(candidate)}
