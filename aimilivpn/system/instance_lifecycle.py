from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
PREFERRED_RESOURCE_SLOTS = {"JP": 0, "US": 1, "KR": 2}
RESOURCE_SLOT_COUNT = 100
RESOURCE_BASES = {"tun_dev": 10, "policy_table": 110, "proxy_port": 7928, "ui_port": 18788}
LEGACY_COUNTRY_CATALOG = (
    {"country": "JP", "name": "Japan", "node_count": 1},
    {"country": "KR", "name": "Korea Republic of", "node_count": 1},
    {"country": "US", "name": "United States", "node_count": 1},
)


class LifecycleError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class InstanceLifecycle:
    config_dir: Path
    install_dir: Path
    instances_file: Path
    token_file: Path
    systemctl: Callable[[list[str]], Any]
    lock: threading.RLock
    resource_probe: Callable[[dict[str, Any]], list[str]] | None = None
    country_catalog: Callable[[], list[dict[str, Any]]] | None = None

    def catalog(self) -> list[dict[str, Any]]:
        with self.lock:
            instances = self._instances()
            installed = {
                str(item.get("country") or "").strip().upper(): item
                for item in instances
            }
            catalog: list[dict[str, Any]] = []
            for source in self._country_entries(instances):
                country = source["country"]
                record = installed.get(country)
                if record is not None:
                    resources = {
                        field: record.get(field)
                        for field in ("tun_dev", "policy_table", "proxy_port", "ui_port")
                    }
                    catalog.append({**source, "id": str(record.get("id") or country.lower()), **resources, "installed": True, "creatable": False})
                    continue
                try:
                    selected = self._allocate_resources(country, instances, check_host=False)
                    catalog.append({**source, **selected, "installed": False, "creatable": True})
                except LifecycleError as exc:
                    catalog.append(
                        {
                            **source,
                            "id": country.lower(),
                            "installed": False,
                            "creatable": False,
                            "error_code": exc.code,
                        }
                    )
            return catalog

    def validate_create(self, country: str, instance_id: str = "") -> dict[str, Any]:
        with self.lock:
            country = str(country or "").strip().upper()
            if not COUNTRY_CODE_PATTERN.fullmatch(country):
                raise LifecycleError("invalid_country", "country must be an ISO alpha-2 code")
            instances = self._instances()
            available = {item["country"] for item in self._country_entries(instances) if int(item.get("node_count") or 0) > 0}
            if country not in available:
                raise LifecycleError("country_not_available", "country is not available in the current VPNGate catalog", 409)
            expected_id = country.lower()
            requested_id = str(instance_id or expected_id).strip().lower()
            if requested_id != expected_id:
                raise LifecycleError("invalid_instance_id", "instance id must match the country code")
            if any(str(item.get("id") or "").lower() == requested_id for item in instances):
                raise LifecycleError("instance_exists", "instance already exists", 409)
            env_file = self.config_dir / f"{requested_id}.env"
            if env_file.exists():
                raise LifecycleError("resource_conflict", "managed environment file already exists", 409)
            return self._allocate_resources(country, instances, check_host=True)

    def _country_entries(self, instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            raw_entries = list(self.country_catalog()) if self.country_catalog is not None else list(LEGACY_COUNTRY_CATALOG)
        except Exception as exc:
            raise LifecycleError("country_catalog_unavailable", "VPNGate country catalog is unavailable", 503) from exc
        entries: dict[str, dict[str, Any]] = {}
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            country = str(item.get("country") or "").strip().upper()
            if not COUNTRY_CODE_PATTERN.fullmatch(country):
                continue
            try:
                node_count = max(0, int(item.get("node_count") or 0))
            except (TypeError, ValueError):
                node_count = 0
            entry = entries.setdefault(
                country,
                {
                    "country": country,
                    "name": str(item.get("name") or country).strip() or country,
                    "node_count": 0,
                },
            )
            entry["node_count"] = max(int(entry["node_count"]), node_count)
        for instance in instances:
            country = str(instance.get("country") or "").strip().upper()
            if COUNTRY_CODE_PATTERN.fullmatch(country):
                entries.setdefault(country, {"country": country, "name": country, "node_count": 0})
        return sorted(
            entries.values(),
            key=lambda item: (0 if item["country"] == "JP" else 1, str(item["name"]).lower(), item["country"]),
        )

    def _allocate_resources(
        self,
        country: str,
        instances: list[dict[str, Any]],
        *,
        check_host: bool,
    ) -> dict[str, Any]:
        preferred = PREFERRED_RESOURCE_SLOTS.get(country)
        reserved = set(PREFERRED_RESOURCE_SLOTS.values())
        slots = ([preferred] if preferred is not None else []) + [
            slot
            for slot in range(RESOURCE_SLOT_COUNT)
            if slot not in reserved and slot != preferred
        ]
        last_host_conflicts: list[str] = []
        for slot in slots:
            selected = {
                "country": country,
                "id": country.lower(),
                "tun_dev": f"tun{RESOURCE_BASES['tun_dev'] + slot}",
                "policy_table": RESOURCE_BASES["policy_table"] + slot,
                "proxy_port": RESOURCE_BASES["proxy_port"] + slot,
                "ui_port": RESOURCE_BASES["ui_port"] + slot,
            }
            if self._catalog_resource_conflicts(selected, instances):
                continue
            host_conflicts = self.resource_probe(selected) if check_host and self.resource_probe is not None else []
            if host_conflicts:
                last_host_conflicts = list(host_conflicts)
                continue
            return selected
        if last_host_conflicts:
            raise LifecycleError(
                "resource_conflict",
                f"host resource conflict: {', '.join(sorted(set(last_host_conflicts)))}",
                409,
            )
        raise LifecycleError("resource_capacity_exhausted", "no managed instance resources are available", 409)

    @staticmethod
    def _catalog_resource_conflicts(selected: dict[str, Any], instances: list[dict[str, Any]]) -> bool:
        return any(
            str(item.get(field) or "") == str(selected[field])
            for item in instances
            for field in ("tun_dev", "policy_table", "proxy_port", "ui_port")
        )

    def create(self, country: str, instance_id: str = "") -> dict[str, Any]:
        with self.lock:
            selected = self.validate_create(country, instance_id)
            instance_id = selected["id"]
            env_file = self.config_dir / f"{instance_id}.env"
            data_dir = self.install_dir / "data" / instance_id
            self._validate_data_path(data_dir, instance_id)
            service = f"aimilivpn@{instance_id}.service"
            token = self._read_token()
            record = {
                "id": instance_id,
                "country": selected["country"],
                "service": service,
                "env_file": str(env_file),
                "data_dir": str(data_dir),
                "ui_host": "127.0.0.1",
                "ui_port": selected["ui_port"],
                "proxy_host": "127.0.0.1",
                "proxy_port": selected["proxy_port"],
                "tun_dev": selected["tun_dev"],
                "policy_table": selected["policy_table"],
            }
            previous_catalog = self.instances_file.read_bytes() if self.instances_file.exists() else None
            data_created = not data_dir.exists()
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                self._atomic_write(env_file, self._env_text(record, token).encode("utf-8"))
                self._write_instances([*self._instances(), record])
                self._systemctl_required(["daemon-reload"])
                self._systemctl_required(["enable", "--now", service])
            except Exception as exc:
                self._rollback_create(service, env_file, data_dir, data_created, previous_catalog)
                if isinstance(exc, LifecycleError):
                    raise
                print(f"[console audit] instance create failed: {type(exc).__name__}", flush=True)
                raise LifecycleError("instance_create_failed", "instance creation failed", 500) from exc
            print(f"[console audit] instance created id={instance_id} country={selected['country']}", flush=True)
            return dict(record)

    def delete(
        self,
        instance_id: str,
        *,
        confirmation: str,
        retain_data: bool = True,
        purge_data_confirmation: str = "",
    ) -> dict[str, Any]:
        instance_id = str(instance_id or "").strip().lower()
        if confirmation != instance_id:
            raise LifecycleError("confirmation_required", "instance deletion confirmation is required")
        if not retain_data and purge_data_confirmation != f"purge:{instance_id}":
            raise LifecycleError("data_confirmation_required", "data deletion requires separate confirmation")
        with self.lock:
            instances = self._instances()
            record = next((item for item in instances if str(item.get("id") or "").lower() == instance_id), None)
            if record is None:
                raise LifecycleError("instance_not_found", "实例不存在", 404)
            expected_env = (self.config_dir / f"{instance_id}.env").resolve(strict=False)
            env_file = Path(str(record.get("env_file") or expected_env)).resolve(strict=False)
            if env_file != expected_env:
                raise LifecycleError("unmanaged_instance", "instance environment is not managed", 409)
            data_dir = Path(str(record.get("data_dir") or ""))
            expected_data = self.install_dir / "data" / instance_id
            if Path(os.path.abspath(data_dir)) != Path(os.path.abspath(expected_data)):
                raise LifecycleError("unmanaged_instance", "instance data path is not managed", 409)
            self._validate_data_path(data_dir, instance_id)
            service = f"aimilivpn@{instance_id}.service"
            previous_catalog = self.instances_file.read_bytes()
            previous_env = env_file.read_bytes() if env_file.exists() else None
            quarantine = data_dir.with_name(f".{instance_id}.delete-pending")
            try:
                self._systemctl_required(["disable", "--now", service])
                if not retain_data and data_dir.exists():
                    if quarantine.exists():
                        raise LifecycleError("data_cleanup_conflict", "data cleanup staging path exists", 409)
                    data_dir.replace(quarantine)
                env_file.unlink(missing_ok=True)
                self._write_instances([item for item in instances if item is not record])
                self._systemctl_required(["daemon-reload"])
                if quarantine.exists():
                    shutil.rmtree(quarantine)
            except Exception as exc:
                self._restore_file(self.instances_file, previous_catalog)
                if previous_env is not None:
                    self._restore_file(env_file, previous_env)
                if quarantine.exists() and not data_dir.exists():
                    quarantine.replace(data_dir)
                try:
                    self.systemctl(["daemon-reload"])
                    self.systemctl(["enable", "--now", service])
                except Exception:
                    pass
                if isinstance(exc, LifecycleError):
                    raise
                print(f"[console audit] instance delete failed: {type(exc).__name__}", flush=True)
                raise LifecycleError("instance_delete_failed", "instance deletion failed", 500) from exc
            print(f"[console audit] instance deleted id={instance_id} retain_data={retain_data}", flush=True)
            return {"id": instance_id, "deleted": True, "data_retained": retain_data, "data_dir": str(data_dir)}

    def _instances(self) -> list[dict[str, Any]]:
        if not self.instances_file.exists():
            return []
        try:
            payload = json.loads(self.instances_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LifecycleError("instance_catalog_invalid", "instance catalog is invalid", 500) from exc
        items = payload.get("instances") if isinstance(payload, dict) else None
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise LifecycleError("instance_catalog_invalid", "instance catalog is invalid", 500)
        return [dict(item) for item in items]

    def _read_token(self) -> str:
        try:
            token = self.token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise LifecycleError("instance_token_missing", "instance API token is unavailable", 500) from exc
        if not token or "\n" in token or "\r" in token:
            raise LifecycleError("instance_token_invalid", "instance API token is invalid", 500)
        return token

    def _validate_data_path(self, data_dir: Path, instance_id: str) -> None:
        base = (self.install_dir / "data").resolve(strict=False)
        expected = base / instance_id
        if data_dir.resolve(strict=False) != expected or data_dir.is_symlink():
            raise LifecycleError("unmanaged_instance", "instance data path is not managed", 409)

    def _write_instances(self, instances: list[dict[str, Any]]) -> None:
        payload = json.dumps({"version": 1, "instances": instances}, ensure_ascii=False, indent=2)
        self._atomic_write(self.instances_file, payload.encode("utf-8"))

    def _atomic_write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        try:
            tmp.write_bytes(data)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        finally:
            tmp.unlink(missing_ok=True)

    def _restore_file(self, path: Path, data: bytes | None) -> None:
        if data is None:
            path.unlink(missing_ok=True)
        else:
            self._atomic_write(path, data)

    def _systemctl_required(self, args: list[str]) -> None:
        result = self.systemctl(args)
        if int(getattr(result, "returncode", 1)) != 0:
            raise LifecycleError("systemctl_failed", "服务操作失败", 500)

    def _rollback_create(
        self,
        service: str,
        env_file: Path,
        data_dir: Path,
        data_created: bool,
        previous_catalog: bytes | None,
    ) -> None:
        try:
            self.systemctl(["disable", "--now", service])
        except Exception:
            pass
        self._restore_file(self.instances_file, previous_catalog)
        env_file.unlink(missing_ok=True)
        if data_created:
            try:
                data_dir.rmdir()
            except OSError:
                pass
        try:
            self.systemctl(["daemon-reload"])
        except Exception:
            pass

    @staticmethod
    def _env_text(record: dict[str, Any], token: str) -> str:
        values = {
            "INSTANCE_ID": record["id"],
            "TUN_DEV": record["tun_dev"],
            "POLICY_TABLE": record["policy_table"],
            "LOCAL_PROXY_HOST": record["proxy_host"],
            "LOCAL_PROXY_PORT": record["proxy_port"],
            "UI_HOST": record["ui_host"],
            "UI_PORT": record["ui_port"],
            "VPNGATE_DATA_DIR": record["data_dir"],
            "ALLOWED_COUNTRIES": record["country"],
            "EXCLUDE_DATACENTER": 1,
            "INSTANCE_API_TOKEN": token,
            "NODE_TEST_WORKERS": 2,
            "MAX_MAINTENANCE_TEST_NODES": 18,
            "OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS": 8,
            "NODE_RETEST_INTERVAL_SECONDS": 21600,
        }
        return "".join(f"{key}={value}\n" for key, value in values.items())


def detect_host_resource_conflicts(selected: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    for field in ("proxy_port", "ui_port"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", int(selected[field])))
        except OSError:
            conflicts.append(field)
        finally:
            sock.close()
    tun_dev = str(selected.get("tun_dev") or "")
    if tun_dev and (Path("/sys/class/net") / tun_dev).exists():
        conflicts.append("tun_dev")
    table = str(selected.get("policy_table") or "")
    if table:
        try:
            result = subprocess.run(
                ["ip", "rule", "show"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and re.search(rf"\b(?:lookup|table)\s+{re.escape(table)}\b", result.stdout):
                conflicts.append("policy_table")
        except (OSError, subprocess.SubprocessError):
            pass
    return conflicts
