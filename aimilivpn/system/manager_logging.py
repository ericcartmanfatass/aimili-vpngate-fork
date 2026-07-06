from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from aimilivpn.system.json_logs import JsonLogWriter, cleanup_json_logs


@dataclass
class ManagerJsonLogRuntime:
    data_dir: Path
    lock: object
    redact_message: Callable[[str], str]
    cleanup_state: dict[str, float] = field(default_factory=dict)

    def writer(self) -> JsonLogWriter:
        return JsonLogWriter(
            logs_dir=self.data_dir / "logs",
            lock=self.lock,
            redact_message=self.redact_message,
            cleanup_state=self.cleanup_state,
        )

    def cleanup_old_logs(self, logs_dir: Path) -> None:
        cleanup_json_logs(logs_dir, self.lock, self.cleanup_state)

    def log_to_json(self, level: str, module: str, message: str) -> None:
        self.writer().write(level, module, message)
