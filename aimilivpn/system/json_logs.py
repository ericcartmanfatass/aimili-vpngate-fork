from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, MutableMapping


CleanupState = MutableMapping[str, float]


@dataclass(frozen=True)
class JsonLogWriter:
    logs_dir: Path
    lock: Any
    redact_message: Callable[[str], str]
    cleanup_state: CleanupState

    def write(self, level: str, module: str, message: str) -> None:
        try:
            self.logs_dir.mkdir(exist_ok=True, parents=True)
            now = time.time()
            date_str = time.strftime("%Y-%m-%d", time.localtime(now))
            log_file = self.logs_dir / f"{date_str}.json"
            entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                "level": level,
                "module": module,
                "message": self.redact_message(message),
            }
            with self.lock:
                with open(log_file, "a", encoding="utf-8") as file:
                    file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            cleanup_json_logs(self.logs_dir, self.lock, self.cleanup_state, now=now)
        except Exception as exc:
            print(f"[Log Error] Failed to write JSON log: {exc}", flush=True)


def cleanup_json_logs(
    logs_dir: Path,
    lock: Any,
    cleanup_state: CleanupState,
    *,
    now: float | None = None,
) -> None:
    current_time = time.time() if now is None else now
    with lock:
        if current_time - cleanup_state.get("last_cleanup_time", 0.0) < 3600:
            return
        cleanup_state["last_cleanup_time"] = current_time

    try:
        three_days_seconds = 3 * 24 * 60 * 60
        today_str = time.strftime("%Y-%m-%d", time.localtime(current_time))
        today_time = time.mktime(time.strptime(today_str, "%Y-%m-%d"))
        for path in logs_dir.glob("*.json"):
            match = re.match(r"^(\d{4}-\d{2}-\d{2})\.json$", path.name)
            if match:
                date_str = match.group(1)
                try:
                    file_time = time.mktime(time.strptime(date_str, "%Y-%m-%d"))
                    if today_time - file_time >= three_days_seconds:
                        with lock:
                            path.unlink()
                        print(f"[清理] 已删除 3 天前的旧日志文件: {path.name}", flush=True)
                except Exception:
                    if current_time - path.stat().st_mtime > three_days_seconds:
                        with lock:
                            path.unlink()
    except Exception as exc:
        print(f"[清理错误] 清理旧日志失败: {exc}", flush=True)
