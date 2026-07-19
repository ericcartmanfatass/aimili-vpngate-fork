from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable


OperationTask = Callable[[], Any]
ThreadStarter = Callable[[Callable[[], None]], None]


class OperationCapacityError(RuntimeError):
    pass


@dataclass
class OperationRecord:
    id: str
    kind: str
    status: str
    created_at: float
    updated_at: float
    idempotency_key: str
    result: Any = None
    error_code: str | None = None

    def public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("idempotency_key", None)
        payload["result"] = _public_result(payload.get("result"))
        return payload


class OperationRegistry:
    def __init__(self, *, clock: Callable[[], float] | None = None, max_records: int = 500) -> None:
        self.clock = clock or time.time
        self.max_records = max(10, int(max_records))
        self._lock = threading.RLock()
        self._records: dict[str, OperationRecord] = {}
        self._keys: dict[tuple[str, str], str] = {}

    def submit(
        self,
        kind: str,
        idempotency_key: str,
        task: OperationTask,
        *,
        start_thread: ThreadStarter,
        reuse_completed: bool,
    ) -> tuple[OperationRecord, bool]:
        kind = str(kind or "").strip()
        key = str(idempotency_key or "").strip()
        if not kind or not key:
            raise ValueError("operation kind and idempotency key are required")
        with self._lock:
            existing_id = self._keys.get((kind, key))
            existing = self._records.get(existing_id or "")
            if existing is not None and (existing.status in {"queued", "running"} or reuse_completed):
                return existing, True
            self._prune_locked(reserve=1)
            if len(self._records) >= self.max_records:
                raise OperationCapacityError("operation registry is at capacity")
            now = self.clock()
            record = OperationRecord(
                id=uuid.uuid4().hex,
                kind=kind,
                status="queued",
                created_at=now,
                updated_at=now,
                idempotency_key=key,
            )
            self._records[record.id] = record
            self._keys[(kind, key)] = record.id

        def run() -> None:
            self._set_status(record.id, "running")
            try:
                result = task()
            except Exception as exc:
                print(f"[Web 审计] 后台操作失败 kind={kind}；异常类型: {type(exc).__name__}", flush=True)
                self._complete(record.id, status="failed", error_code=f"{kind}_failed")
                return
            self._complete(record.id, status="succeeded", result=result)

        try:
            start_thread(run)
        except Exception:
            self._complete(record.id, status="failed", error_code="operation_start_failed")
            raise
        return record, False

    def get(self, operation_id: str) -> OperationRecord | None:
        with self._lock:
            return self._records.get(str(operation_id or ""))

    def list(self) -> list[OperationRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)

    def _set_status(self, operation_id: str, status: str) -> None:
        with self._lock:
            record = self._records.get(operation_id)
            if record is not None:
                record.status = status
                record.updated_at = self.clock()

    def _complete(
        self,
        operation_id: str,
        *,
        status: str,
        result: Any = None,
        error_code: str | None = None,
    ) -> None:
        with self._lock:
            record = self._records.get(operation_id)
            if record is not None:
                record.status = status
                record.result = _public_result(result)
                record.error_code = error_code
                record.updated_at = self.clock()

    def _prune_locked(self, *, reserve: int = 0) -> None:
        target_size = max(0, self.max_records - reserve)
        if len(self._records) <= target_size:
            return
        completed = sorted(
            (record for record in self._records.values() if record.status not in {"queued", "running"}),
            key=lambda item: item.updated_at,
        )
        for record in completed[: max(0, len(self._records) - target_size)]:
            self._records.pop(record.id, None)
            key = (record.kind, record.idempotency_key)
            if self._keys.get(key) == record.id:
                self._keys.pop(key, None)


def _public_result(value: Any) -> Any:
    sensitive = {"config_text", "password", "password_hash", "raw_response", "proxy_auth"}
    if isinstance(value, dict):
        return {
            str(key): _public_result(item)
            for key, item in value.items()
            if str(key).lower() not in sensitive
        }
    if isinstance(value, (list, tuple)):
        return [_public_result(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None
