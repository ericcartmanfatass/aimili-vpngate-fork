from __future__ import annotations

"""Console-facing facade for global settings, snapshots and backups."""

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping

from aimilivpn.core.global_backup import (
    BackupManager,
    BackupRestoreError,
    build_backup_payload,
    document_checksum as backup_checksum,
    preview_backup,
    validate_backup_payload,
)
from aimilivpn.core.global_config import (
    APP_VERSION,
    GlobalConfigError,
    global_settings_for_runtime,
    load_global_secrets,
    public_global_settings,
    save_global_settings,
)
from aimilivpn.core.global_nodes import build_country_index, write_global_nodes
from aimilivpn.core.global_quality import QualityBatchProcessor
from aimilivpn.core.global_storage import GlobalRepository
from aimilivpn.core.storage import SqliteStore, migration_summary_status
from aimilivpn.providers.scamalytics import ScamalyticsProvider
from aimilivpn.system.console_instances import load_instances, parse_env_file, read_logs
from aimilivpn.system.global_scheduler import GlobalScheduler


INSTANCE_PREFERENCE_KEYS = (
    "routing_mode",
    "force_country",
    "routing_ip_type",
    "connection_enabled",
    "fixed_node_id",
    "favorite_node_ids",
    "fav_fail_fallback",
)


def _atomic_write(path: Path, payload: Any) -> None:
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
    finally:
        tmp.unlink(missing_ok=True)


@dataclass
class GlobalConsoleRuntime:
    config_dir: Path
    install_dir: Path
    scheduler: GlobalScheduler

    @classmethod
    def build(cls, config_dir: Path, install_dir: Path) -> "GlobalConsoleRuntime":
        runtime = cls.__new__(cls)
        runtime.config_dir = Path(config_dir)
        runtime.install_dir = Path(install_dir)
        snapshot_dir = runtime.install_dir / "data" / "global"
        storage_backend = os.environ.get("AIMILIVPN_GLOBAL_STORAGE_BACKEND", "sqlite").strip().lower() or "sqlite"
        repository = GlobalRepository(snapshot_dir, backend=storage_backend)
        runtime.migration_result = repository.migrate_json()
        runtime.scheduler = GlobalScheduler(
            runtime.config_dir,
            runtime.install_dir / "data",
            repository=repository,
            publish=runtime.publish_snapshot,
            quality_runner=runtime.run_quality_batch,
        )
        return runtime

    @property
    def preferences_path(self) -> Path:
        return self.config_dir / "global_instance_preferences.json"

    @property
    def regions_path(self) -> Path:
        return self.install_dir / "data" / "global" / "regions.json"

    @property
    def restore_status_path(self) -> Path:
        return self.config_dir / "last_restore_status.json"

    def settings(self) -> dict[str, Any]:
        return public_global_settings(self.config_dir)

    def save_settings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        updates = dict(payload)
        api_key = updates.pop("scamalytics_api_key", None)
        if api_key is not None and not isinstance(api_key, str):
            raise GlobalConfigError("Scamalytics API Key 必须是文本")
        save_global_settings(self.config_dir, updates, scamalytics_api_key=api_key)
        return self.settings()

    def task_status(self) -> dict[str, Any]:
        status = self.scheduler.status()
        status["history"] = self.scheduler.repository.read_history(limit=100)
        status["quality_queue"] = self.scheduler.repository.read_quality_queue()
        status["quality_cache_count"] = len(self.scheduler.repository.read_quality())
        status["quality_metrics"] = self.scheduler.repository.read_quality_metrics()
        return status

    def logs_security(self) -> dict[str, Any]:
        instance_logs = []
        for instance in load_instances():
            entries = read_logs(instance).get("logs", [])
            instance_logs.append({"id": instance["id"], "country": instance["country"], "logs": entries[-100:]})
        settings = self.settings()
        return {
            "global_history": self.scheduler.repository.read_history(limit=100),
            "instances": instance_logs,
            "security": {
                "storage_backend": self.scheduler.repository.backend,
                "storage_health": self.scheduler.repository.health_status(),
                "last_migration": getattr(self, "migration_result", {}),
                "secret_storage_separate": True,
                "api_key_configured": bool(settings.get("scamalytics_api_key_configured")),
                "backup_directory": str(self.config_dir / "backups"),
                "latest_backup": self._latest_backup_status(),
                "last_restore": getattr(
                    self,
                    "last_restore",
                    self._read_json(self.restore_status_path, {}),
                ),
                "instance_storage": self._instance_storage_status(),
                "log_retention_days": settings.get("json_log_retention_days"),
                "text_log_max_bytes": settings.get("text_log_max_bytes"),
                "text_log_backup_count": settings.get("text_log_backup_count"),
            },
        }

    def _latest_backup_status(self) -> dict[str, Any]:
        backup_dir = self.config_dir / "backups"
        candidates: list[tuple[float, Path]] = []
        for path in backup_dir.glob("aimilivpn-v*.json"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            return {}
        updated_at, path = candidates[0]
        status: dict[str, Any] = {
            "path": str(path),
            "updated_at": updated_at,
            "validated": False,
            "checksum": "",
        }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validated = validate_backup_payload(payload)
            status["validated"] = True
            status["checksum"] = backup_checksum(validated)
            status["backup_type"] = validated.get("backup_type")
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return status

    def _instance_storage_status(self) -> list[dict[str, Any]]:
        statuses: list[dict[str, Any]] = []
        for instance in load_instances():
            env = parse_env_file(Path(str(instance.get("env_file") or "")))
            backend = str(env.get("STORAGE_BACKEND") or "sqlite").strip().lower()
            data_dir = Path(str(instance.get("data_dir") or ""))
            db_path = Path(env.get("SQLITE_DB_PATH") or data_dir / "aimilivpn.db")
            if not db_path.is_absolute():
                db_path = data_dir / db_path
            item: dict[str, Any] = {
                "id": str(instance.get("id") or ""),
                "backend": backend if backend in {"json", "sqlite"} else "sqlite",
                "ok": True,
                "path": str(db_path) if backend != "json" else str(data_dir),
                "migration": None,
            }
            if item["backend"] == "sqlite" and db_path.exists():
                store = SqliteStore(db_path)
                item.update(store.health_status())
                summary = store.latest_migration_summary()
                item["migration"] = migration_summary_status(summary)
            elif item["backend"] == "sqlite":
                item["ok"] = False
                item["quick_check"] = "missing"
            statuses.append(item)
        return statuses

    def nodes(self) -> dict[str, Any]:
        quality_cache = self.scheduler.repository.read_quality()
        nodes = []
        for node in self.scheduler.read_nodes():
            item = dict(node)
            item.pop("config_text", None)
            ip = str(item.get("server_ip") or item.get("ip") or "")
            if ip and isinstance(quality_cache.get(ip), dict):
                item["quality_result"] = dict(quality_cache[ip])
            nodes.append(item)
        return {"nodes": nodes, "task": self.task_status()}

    def refresh(self) -> dict[str, Any]:
        return self.scheduler.run_once(reason="manual")

    def run_quality_batch(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        settings = global_settings_for_runtime(self.config_dir)
        if not settings.get("scamalytics_enabled"):
            return {"status": "disabled", "unique_ips": 0, "cache_hits": 0, "requested": 0, "failed": 0, "deferred": 0, "quality_metrics": self.scheduler.repository.read_quality_metrics()}
        username = str(settings.get("scamalytics_username") or "")
        api_key = str(settings.get("scamalytics_api_key") or "")
        if not username or not api_key:
            return {"status": "not_configured", "unique_ips": 0, "cache_hits": 0, "requested": 0, "failed": 0, "deferred": 0, "quality_metrics": self.scheduler.repository.read_quality_metrics()}
        provider = ScamalyticsProvider(
            username=username,
            api_key=api_key,
            api_url=str(settings.get("scamalytics_api_url") or ""),
            timeout_seconds=int(settings.get("scamalytics_timeout_seconds") or 8),
            cache_ttl_seconds=int(settings.get("scamalytics_cache_ttl_days") or 7) * 86400,
            rate_limit_per_minute=int(settings.get("scamalytics_rate_limit_per_minute") or 30),
        )
        processor = QualityBatchProcessor(
            self.scheduler.snapshot_dir / "quality_results.json",
            cache_ttl_seconds=provider.cache_ttl_seconds,
            rate_limit_per_minute=provider.rate_limit_per_minute,
            repository=self.scheduler.repository,
            retry_backoff_seconds=(300, 900, 1800, 3600),
            daily_quota=int(settings.get("scamalytics_daily_quota") or 1000),
        )

        def query(ip: str) -> dict[str, Any]:
            result = provider.check_ip(ip)
            data = asdict(result)
            data.pop("raw_response", None)
            return data

        summary = processor.run(nodes, query)
        return {"status": "ok", **summary.to_dict(), "quality_metrics": self.scheduler.repository.read_quality_metrics()}

    def test_scamalytics(self) -> dict[str, Any]:
        settings = global_settings_for_runtime(self.config_dir)
        if not settings.get("scamalytics_enabled"):
            return {"ok": False, "error_code": "scamalytics_disabled", "error": "Scamalytics 当前未启用", "message": "Scamalytics 当前未启用"}
        username = str(settings.get("scamalytics_username") or "")
        api_key = str(settings.get("scamalytics_api_key") or "")
        if not username or not api_key:
            return {"ok": False, "error_code": "scamalytics_not_configured", "error": "请先填写 Scamalytics 凭据", "message": "请先填写 Scamalytics 凭据"}
        provider = ScamalyticsProvider(
            username=username,
            api_key=api_key,
            api_url=str(settings.get("scamalytics_api_url") or ""),
            timeout_seconds=int(settings.get("scamalytics_timeout_seconds") or 8),
        )
        try:
            provider.check_ip("198.51.100.1")
        except Exception:
            return {"ok": False, "error_code": "scamalytics_test_failed", "error": "Scamalytics 连通性或凭据校验失败", "message": "Scamalytics 连通性或凭据校验失败"}
        return {"ok": True, "message": "Scamalytics 连通性和凭据校验成功"}

    def backup_payload(self, backup_type: str = "config") -> dict[str, Any]:
        instances = []
        for instance in load_instances():
            data_dir = str(instance.get("data_dir") or "").strip()
            ui_config = self._read_json(Path(data_dir) / "ui_auth.json", {}) if data_dir else {}
            preferences = {
                key: ui_config[key]
                for key in INSTANCE_PREFERENCE_KEYS
                if isinstance(ui_config, dict) and key in ui_config
            }
            instances.append(
                {"id": instance["id"], "country": instance["country"], "preferences": preferences}
            )
        regions = self._read_regions()
        nodes = []
        for node in self.scheduler.read_nodes():
            item = dict(node)
            item.pop("config_text", None)
            item.pop("config_file", None)
            nodes.append(item)
        return build_backup_payload(
            global_settings=self.settings(),
            instances=instances,
            regions=regions,
            backup_type=backup_type,
            nodes=nodes if backup_type == "full" else None,
            quality_results=list(self.scheduler.repository.read_quality().values()) if backup_type == "full" else None,
            blacklist=self._read_json(self.scheduler.snapshot_dir / "blacklist.json", {}) if backup_type == "full" else None,
            job_history=self.scheduler.repository.read_history() if backup_type == "full" else None,
            quality_metrics=self.scheduler.repository.read_quality_metrics() if backup_type == "full" else None,
        )

    def export_backup(self, backup_type: str = "config") -> dict[str, Any]:
        manager = BackupManager(self.config_dir / "backups")
        _, result = manager.export(self.backup_payload(backup_type))
        result.pop("payload", None)
        return result

    def preview_restore(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        candidate = validate_backup_payload(payload)
        current = self.backup_payload("full" if candidate["backup_type"] == "full" else "config")
        return {"validation": "ok", **preview_backup(current, candidate)}

    def restore(
        self,
        payload: Mapping[str, Any],
        *,
        confirmed: bool,
        confirm_deletions: bool = False,
        sync_instances: Callable[[list[dict[str, Any]]], Any] | None = None,
    ) -> dict[str, Any]:
        if not confirmed:
            raise GlobalConfigError("恢复操作需要二次确认")
        candidate = validate_backup_payload(payload)
        current = self.backup_payload("full" if candidate["backup_type"] == "full" else "config")
        restore_preview = preview_backup(current, candidate)
        if restore_preview.get("requires_deletion_confirmation") and not confirm_deletions:
            raise GlobalConfigError("恢复包含删除项，需要单独确认")

        secrets_before = load_global_secrets(self.config_dir)

        def apply(document: dict[str, Any], *, scamalytics_api_key: str) -> None:
            settings = document.get("global_settings")
            if not isinstance(settings, dict):
                raise GlobalConfigError("缺少全局配置")
            save_global_settings(
                self.config_dir,
                settings,
                scamalytics_api_key=scamalytics_api_key,
            )
            restored_instances = [
                dict(item) for item in document.get("instances", []) if isinstance(item, dict)
            ]
            if sync_instances is not None:
                sync_instances(restored_instances)
            self._restore_instance_preferences(restored_instances)
            _atomic_write(self.preferences_path, restored_instances)
            _atomic_write(self.regions_path, document.get("regions", []))
            if document.get("backup_type") == "full":
                self._restore_business_data(document)

        manager = BackupManager(self.config_dir / "backups")
        try:
            result = manager.restore(
                candidate,
                current=current,
                apply=lambda document: apply(document, scamalytics_api_key=""),
                rollback=lambda document: apply(
                    document,
                    scamalytics_api_key=str(secrets_before.get("scamalytics_api_key") or ""),
                ),
            )
        except BackupRestoreError as exc:
            self.last_restore = {
                "at": time.time(),
                "checksum": backup_checksum(candidate),
                "ok": False,
                "error_code": exc.error_code,
                "rollback_succeeded": exc.rollback_succeeded,
            }
            _atomic_write(self.restore_status_path, self.last_restore)
            raise
        result["preview"] = restore_preview
        self.last_restore = {
            "at": time.time(),
            "backup_before_restore": result.get("backup_before_restore"),
            "checksum": result.get("checksum"),
            "ok": True,
        }
        _atomic_write(self.restore_status_path, self.last_restore)
        public = self.settings()
        result["sensitive_config_required"] = bool(
            public.get("scamalytics_enabled") and not public.get("scamalytics_api_key_configured")
        )
        return result

    def _restore_business_data(self, document: Mapping[str, Any]) -> None:
        """Restore all full-backup data stores and their JSON compatibility views."""
        now = self.scheduler.clock()
        raw_nodes = document.get("nodes", [])
        nodes = [dict(item) for item in raw_nodes if isinstance(item, dict) and str(item.get("id") or "").strip()]
        cleaned: list[dict[str, Any]] = []
        if nodes:
            cleaned = write_global_nodes(
                self.scheduler.nodes_path,
                nodes,
                config_dir=self.scheduler.configs_dir,
                updated_at=now,
            )
        else:
            _atomic_write(
                self.scheduler.nodes_path,
                {
                    "schema_version": 1,
                    "source": "restore",
                    "updated_at": now,
                    "node_count": 0,
                    "nodes": [],
                },
            )
        _atomic_write(self.scheduler.country_index_path, build_country_index(nodes))

        quality_metrics = document.get("quality_metrics", {})
        history = document.get("job_history", [])
        restored_state = {
            "status": "restored",
            "last_finished_at": now,
            "last_success_at": now,
            "last_error": "",
            "failure_count": 0,
            "retry_level": 0,
            "next_retry_at": 0,
            "next_scheduled_at": self.scheduler.next_scheduled_at(now),
            "last_result_node_count": len(nodes),
        }
        quality_results = document.get("quality_results", [])
        self.scheduler.repository.restore_business_bundle(
            nodes=cleaned if nodes else [],
            quality_results=(
                [dict(item) for item in quality_results if isinstance(item, dict)]
                if isinstance(quality_results, list)
                else []
            ),
            quality_metrics=quality_metrics if isinstance(quality_metrics, dict) else {},
            history=(
                [dict(item) for item in history if isinstance(item, dict)]
                if isinstance(history, list)
                else []
            ),
            task_state=restored_state,
            updated_at=now,
        )
        _atomic_write(self.scheduler.snapshot_dir / "blacklist.json", document.get("blacklist", {}))
        if self.scheduler.repository.backend == "sqlite":
            _atomic_write(self.scheduler.state_path, restored_state)
            _atomic_write(self.scheduler.history_path, self.scheduler.repository.read_history(limit=100))
            _atomic_write(self.scheduler.repository.quality_path, self.scheduler.repository.read_quality())
            _atomic_write(self.scheduler.repository.quality_queue_path, {})
            _atomic_write(self.scheduler.repository.quality_metrics_path, self.scheduler.repository.read_quality_metrics())

    def _restore_instance_preferences(self, desired_instances: list[dict[str, Any]]) -> None:
        current_by_id = {str(item.get("id") or ""): item for item in load_instances()}
        for desired in desired_instances:
            instance_id = str(desired.get("id") or "")
            current = current_by_id.get(instance_id)
            if current is None:
                raise GlobalConfigError(f"恢复后未找到实例: {instance_id}")
            preferences = desired.get("preferences", {})
            if not isinstance(preferences, dict):
                raise GlobalConfigError(f"实例偏好格式无效: {instance_id}")
            auth_path = Path(current["data_dir"]) / "ui_auth.json"
            ui_config = self._read_json(auth_path, {})
            ui_config = dict(ui_config) if isinstance(ui_config, dict) else {}
            for key in INSTANCE_PREFERENCE_KEYS:
                if key in preferences:
                    ui_config[key] = preferences[key]
            _atomic_write(auth_path, ui_config)

    def start(self) -> None:
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.stop()

    def publish_snapshot(self, nodes: list[dict[str, Any]]) -> None:
        """Publish country-specific candidates without clearing empty regions."""
        expired_countries = {
            str(country).upper()
            for country in self.scheduler.status().get("country_expired_countries", [])
        }
        for instance in load_instances():
            country = str(instance.get("country") or "").upper()
            selected = [dict(node) for node in nodes if str(node.get("country_short") or "").upper() == country]
            if not selected:
                if country in expired_countries:
                    target_dir = Path(instance["data_dir"])
                    _atomic_write(target_dir / "nodes.json", [])
                continue
            target_dir = Path(instance["data_dir"])
            config_dir = target_dir / "configs"
            config_dir.mkdir(parents=True, exist_ok=True)
            for node in selected:
                source_path = Path(str(node.get("config_file") or ""))
                if not source_path.exists():
                    continue
                target_path = config_dir / f"{str(node.get('id') or 'node')}.ovpn"
                try:
                    shutil.copy2(source_path, target_path)
                except OSError:
                    continue
                node["config_file"] = str(target_path)
                node.pop("config_text", None)
            _atomic_write(target_dir / "nodes.json", selected)

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return default
        return payload

    def _read_regions(self) -> list[dict[str, Any]]:
        payload = self._read_json(self.regions_path, [])
        return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
