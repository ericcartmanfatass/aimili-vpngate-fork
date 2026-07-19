from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aimilivpn.system.json_logs import JsonLogWriter, cleanup_json_logs


@dataclass
class ManagerJsonLogRuntime:
    data_dir: Path
    lock: object
    redact_message: Callable[[str], str]
    retention_days: int = 7
    cleanup_state: dict[str, Any] = field(default_factory=dict)

    def writer(self) -> JsonLogWriter:
        return JsonLogWriter(
            logs_dir=self.data_dir / "logs",
            lock=self.lock,
            redact_message=self.redact_message,
            cleanup_state=self.cleanup_state,
            retention_days=self.retention_days,
        )

    def cleanup_old_logs(self, logs_dir: Path) -> None:
        cleanup_json_logs(
            logs_dir,
            self.lock,
            self.cleanup_state,
            retention_days=self.retention_days,
        )

    def log_to_json(self, level: str, module: str, message: str) -> None:
        self.writer().write(level, module, message)
