from __future__ import annotations

"""Single-process global VPNGate scheduler used by Console."""

import json
import os
import shutil
import threading
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from aimilivpn.core.global_config import GlobalConfigError, GlobalSettings, load_global_settings
from aimilivpn.core.global_nodes import (
    GlobalNodeValidationError,
    build_country_index,
    parse_global_nodes,
    read_global_nodes,
    read_snapshot_payload,
    write_global_nodes,
)
from aimilivpn.core.global_storage import GlobalRepository

try:
    import fcntl
except ImportError:  # pragma: no cover - used on Windows development hosts
    fcntl = None  # type: ignore[assignment]
try:
    import msvcrt
except ImportError:  # pragma: no cover - used on Linux production hosts
    msvcrt = None  # type: ignore[assignment]


class GlobalSchedulerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


class GlobalScheduler:
    """Own one globally shared VPNGate snapshot and its retry state."""

    def __init__(
        self,
        config_dir: Path,
        data_dir: Path,
        *,
        fetcher: Callable[[], str] | None = None,
        clock: Callable[[], float] = time.time,
        wait: Callable[[float], None] = time.sleep,
        logger: Callable[[str, str], None] | None = None,
        publish: Callable[[list[dict[str, Any]]], None] | None = None,
        quality_runner: Callable[[list[dict[str, Any]]], Any] | None = None,
        max_scan_rows: int = 3000,
        repository: GlobalRepository | None = None,
        storage_backend: str = "json",
        global_db_path: Path | None = None,
    ) -> None:
        self.config_dir = Path(config_dir)
        self.data_dir = Path(data_dir)
        self.snapshot_dir = self.data_dir / "global"
        self.configs_dir = self.snapshot_dir / "configs"
        self.nodes_path = self.snapshot_dir / "nodes.json"
        self.previous_nodes_path = self.snapshot_dir / "nodes.previous.json"
        self.country_index_path = self.snapshot_dir / "country_index.json"
        self.state_path = self.snapshot_dir / "task_state.json"
        self.history_path = self.snapshot_dir / "task_history.json"
        self.lock_path = self.snapshot_dir / "task.lock"
        self.repository = repository or GlobalRepository(
            self.snapshot_dir,
            backend=storage_backend,
            db_path=global_db_path,
        )
        self.fetcher = fetcher or self._default_fetcher
        self.clock = clock
        self.wait = wait
        self.logger = logger or (lambda level, message: print(f"[{level}] {message}", flush=True))
        self.publish = publish
        self.quality_runner = quality_runner
        self.max_scan_rows = max(1, int(max_scan_rows))
        self._thread_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def settings(self) -> GlobalSettings:
        return load_global_settings(self.config_dir)

    def read_nodes(self) -> list[dict[str, Any]]:
        nodes = self.repository.read_nodes()
        return nodes if nodes else read_global_nodes(self.nodes_path)

    def status(self) -> dict[str, Any]:
        state = self._read_state()
        payload = read_snapshot_payload(self.nodes_path)
        nodes = self.read_nodes()
        updated_at = self.repository.snapshot_updated_at()
        if updated_at is None and isinstance(payload, dict):
            updated_at = payload.get("updated_at")
        state.update(
            {
                "node_count": len([item for item in nodes if isinstance(item, dict)]),
                "countries": len(build_country_index(item for item in nodes if isinstance(item, dict))),
                "snapshot_updated_at": updated_at,
                "snapshot_path": str(self.nodes_path),
                "next_run_at": state.get("next_scheduled_at") or self.next_scheduled_at(),
            }
        )
        return state

    def next_scheduled_at(self, now: float | None = None) -> float:
        current = self.clock() if now is None else now
        settings = self.settings()
        tz = self._timezone(settings.vpn_gate_timezone)
        local_now = datetime.fromtimestamp(current, tz=tz)
        hour, minute = (int(item) for item in settings.vpn_gate_schedule_time.split(":"))
        scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled.timestamp() <= current:
            scheduled += timedelta(days=1)
        return scheduled.timestamp()

    def run_due(self) -> dict[str, Any]:
        settings = self.settings()
        if not settings.vpn_gate_enabled:
            return {"status": "disabled", "next_run_at": self.next_scheduled_at()}
        state = self.status()
        now = self.clock()
        retry_at = float(state.get("next_retry_at") or 0)
        scheduled_at = float(state.get("next_scheduled_at") or self.next_scheduled_at(now))
        if now < min(value for value in (retry_at, scheduled_at) if value > 0):
            return {"status": "not_due", "next_run_at": min(value for value in (retry_at, scheduled_at) if value > 0)}
        return self.run_once(reason="scheduled")

    def run_once(self, *, reason: str = "manual") -> dict[str, Any]:
        if not self._thread_lock.acquire(blocking=False):
            return {"status": "already_running", "message": "全局节点更新任务正在运行"}
        try:
            with self._process_lock() as acquired:
                if not acquired:
                    return {"status": "already_running", "message": "全局节点更新任务正在运行"}
                return self._run_once_locked(reason)
        finally:
            self._thread_lock.release()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    result = self.run_due()
                    next_run = float(result.get("next_run_at") or self.next_scheduled_at())
                except Exception as exc:  # scheduler must not kill Console
                    self._log_once("scheduler_loop", "ERROR", f"全局调度循环异常: {type(exc).__name__}")
                    next_run = self.clock() + 60
                self._stop.wait(max(1.0, min(300.0, next_run - self.clock())))

        self._thread = threading.Thread(target=loop, name="aimilivpn-global-scheduler", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _run_once_locked(self, reason: str) -> dict[str, Any]:
        started = self.clock()
        old_state = self.status()
        state = dict(old_state)
        state.update({"status": "running", "last_started_at": started, "last_reason": reason, "last_error": ""})
        self._write_state(state)
        try:
            raw = self.fetcher()
            if not isinstance(raw, str):
                raise GlobalSchedulerError("invalid_response", "VPNGate 返回格式无效")
            nodes = parse_global_nodes(raw, config_dir=self.configs_dir, max_scan_rows=self.max_scan_rows)
            if not nodes:
                raise GlobalSchedulerError("empty_response", "VPNGate 返回为空，保留上一份节点快照")
            settings = self.settings()
            snapshot_time = self.clock()
            previous_nodes = self.read_nodes()
            previous_country_times = {
                str(country).upper(): _as_float(value, snapshot_time)
                for country, value in (old_state.get("country_snapshot_updated_at") or {}).items()
                if str(country).strip()
            }
            if previous_nodes and not previous_country_times:
                fallback_time = _as_float(old_state.get("snapshot_updated_at"), snapshot_time)
                previous_country_times = {
                    country: fallback_time
                    for country in {_country_code(node) for node in previous_nodes}
                    if country
                }
            new_countries = {_country_code(node) for node in nodes if _country_code(node)}
            retained_countries: list[str] = []
            expired_countries: list[str] = []
            retained_nodes: list[dict[str, Any]] = []
            for country in sorted(previous_country_times):
                if country in new_countries:
                    continue
                age_seconds = max(0.0, snapshot_time - previous_country_times[country])
                old_country_nodes = [node for node in previous_nodes if _country_code(node) == country]
                if age_seconds <= settings.old_snapshot_grace_hours * 3600 and old_country_nodes:
                    retained_countries.append(country)
                    for old_node in old_country_nodes:
                        retained = dict(old_node)
                        retained["snapshot_country_stale"] = True
                        retained["snapshot_country_updated_at"] = previous_country_times[country]
                        retained["snapshot_country_stale_at"] = previous_country_times[country] + settings.old_snapshot_grace_hours * 3600
                        retained_nodes.append(retained)
                else:
                    expired_countries.append(country)
            for node in nodes:
                node["snapshot_country_stale"] = False
                node["snapshot_country_updated_at"] = snapshot_time
                node.pop("snapshot_country_stale_at", None)
            combined_nodes = _deduplicate_nodes([*nodes, *retained_nodes])
            current_exists = self.nodes_path.exists()
            if current_exists:
                shutil.copy2(self.nodes_path, self.previous_nodes_path)
            cleaned = write_global_nodes(
                self.nodes_path,
                combined_nodes,
                config_dir=self.configs_dir,
                updated_at=snapshot_time,
            )
            self.repository.replace_nodes(cleaned, updated_at=snapshot_time)
            _atomic_json_write(self.country_index_path, build_country_index(cleaned))
            quality_summary: Any = None
            if self.quality_runner is not None:
                try:
                    quality_summary = self.quality_runner(cleaned)
                except Exception as exc:
                    self._log_once("quality:error", "WARNING", f"Scamalytics 批量任务未完成: {type(exc).__name__}")
            finished = self.clock()
            state.update(
                {
                    "status": "ok",
                    "last_finished_at": finished,
                    "last_success_at": finished,
                    "duration_seconds": max(0, finished - started),
                    "last_result_node_count": len(cleaned),
                    "last_error": "",
                    "failure_count": 0,
                    "retry_level": 0,
                    "next_retry_at": 0,
                    "next_scheduled_at": self.next_scheduled_at(finished),
                    "snapshot_stale_at": 0,
                    "country_snapshot_updated_at": {
                        country: snapshot_time for country in sorted(new_countries)
                    } | {
                        country: previous_country_times[country] for country in retained_countries
                    },
                    "country_snapshot_stale_countries": retained_countries,
                    "country_expired_countries": expired_countries,
                    "country_snapshot_grace_hours": settings.old_snapshot_grace_hours,
                    "quality_summary": quality_summary,
                }
            )
            self._append_history({"status": "ok", "reason": reason, "at": finished, "node_count": len(cleaned)})
            self._write_state(state)
            self._log_once("success", "INFO", f"全局 VPNGate 节点更新成功，共 {len(cleaned)} 个节点")
            if self.publish is not None:
                self.publish(cleaned)
            return {"status": "ok", "node_count": len(cleaned), "next_run_at": state["next_scheduled_at"]}
        except Exception as exc:
            finished = self.clock()
            failures = int(old_state.get("failure_count") or 0) + 1
            settings = self.settings()
            backoff = settings.vpn_gate_retry_backoff_seconds
            retry_index = min(failures - 1, len(backoff) - 1)
            retry_at = finished + backoff[retry_index]
            code = getattr(exc, "code", "fetch_failed")
            message = getattr(exc, "message", "全局节点更新失败")
            if isinstance(exc, GlobalNodeValidationError):
                code = "empty_response" if any(token in str(exc) for token in ("返回为空", "没有可用节点")) else "invalid_response"
                message = str(exc)
            stale_at = 0
            if self.nodes_path.exists():
                stale_at = finished + settings.old_snapshot_grace_hours * 3600
            state.update(
                {
                    "status": "error",
                    "last_finished_at": finished,
                    "duration_seconds": max(0, finished - started),
                    "last_error_code": code,
                    "last_error": message,
                    "failure_count": failures,
                    "retry_level": retry_index + 1,
                    "next_retry_at": retry_at,
                    "next_scheduled_at": self.next_scheduled_at(finished),
                    "snapshot_stale_at": stale_at,
                }
            )
            self._append_history({"status": "error", "reason": reason, "at": finished, "error_code": code})
            self._write_state(state)
            self._log_once(f"error:{code}:{retry_index}", "ERROR", f"全局 VPNGate 更新失败（{code}），将在退避后重试")
            return {"status": "error", "error_code": code, "message": message, "next_run_at": retry_at}

    def _default_fetcher(self) -> str:
        request = urllib.request.Request(
            self.settings().vpn_gate_api_url,
            headers={"User-Agent": "AimiliVPN/1.0.2", "Accept": "text/plain,*/*"},
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def _timezone(name: str) -> timezone | ZoneInfo:
        if name == "local":
            return datetime.now().astimezone().tzinfo or timezone.utc
        if name.upper() in {"UTC", "GMT", "ETC/UTC"}:
            return timezone.utc
        return ZoneInfo(name)

    @contextmanager
    def _process_lock(self) -> Iterator[bool]:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+b")
        acquired = True
        try:
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (BlockingIOError, OSError):
                    acquired = False
            elif msvcrt is not None:
                try:
                    handle.seek(0)
                    handle.write(b"0")
                    handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    acquired = False
            yield acquired
        finally:
            if acquired and fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            elif acquired and msvcrt is not None:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            handle.close()

    def _append_history(self, item: dict[str, Any]) -> None:
        self.repository.append_history(item, limit=100)
        if self.repository.backend == "sqlite":
            history = self.repository.read_history(limit=100)
            _atomic_json_write(self.history_path, history)

    def _read_state(self) -> dict[str, Any]:
        state = self.repository.read_task_state()
        return state if state else _read_json(self.state_path, {})

    def _write_state(self, state: dict[str, Any]) -> None:
        self.repository.write_task_state(state)
        if self.repository.backend == "sqlite":
            _atomic_json_write(self.state_path, state)

    def _log_once(self, key: str, level: str, message: str) -> None:
        state = self._read_state()
        if state.get("last_log_key") == key:
            return
        state["last_log_key"] = key
        self._write_state(state)
        self.logger(level, message)


def _country_code(node: dict[str, Any]) -> str:
    return str(node.get("country_short") or node.get("country_code") or "").strip().upper()


def _deduplicate_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_ips: set[str] = set()
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        ip = str(node.get("server_ip") or node.get("ip") or "").strip()
        if not node_id or node_id in seen_ids or (ip and ip in seen_ips):
            continue
        result.append(node)
        seen_ids.add(node_id)
        if ip:
            seen_ips.add(ip)
    return result


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
