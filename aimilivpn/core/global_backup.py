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
        raise BackupValidationError("backup_type must be config or full")
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


def _validate_safe_system_fields(payload: Mapping[str, Any]) -> None:
    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in _FORBIDDEN_SYSTEM_KEYS:
                    raise BackupValidationError(f"备份不允许指定系统资源: {path}{key}")
                walk(item, f"{path}{key}.")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}{index}.")
    walk(payload)


def preview_backup(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    current_clean = strip_sensitive(dict(current))
    candidate_clean = validate_backup_payload(candidate)
    changes: list[dict[str, Any]] = []
    for key in sorted(set(current_clean) | set(candidate_clean)):
        if key in {"exported_at", "app_version"}:
            continue
        if current_clean.get(key) != candidate_clean.get(key):
            before = current_clean.get(key)
            after = candidate_clean.get(key)
            if key == "instances" and isinstance(before, list) and isinstance(after, list):
                before_ids = {str(item.get("id")) for item in before if isinstance(item, dict)}
                after_ids = {str(item.get("id")) for item in after if isinstance(item, dict)}
                detail = {"added": sorted(after_ids - before_ids), "removed": sorted(before_ids - after_ids)}
            else:
                detail = {"changed": True}
            changes.append({"field": key, **detail})
    return {"changed": bool(changes), "change_count": len(changes), "changes": changes}


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
        except Exception:
            try:
                apply(before)
            except Exception:
                pass
            raise
        return {"ok": True, "backup_before_restore": str(backup_path), "checksum": document_checksum(candidate)}
