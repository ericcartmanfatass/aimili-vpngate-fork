from __future__ import annotations

import json
import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, MutableMapping


CleanupState = MutableMapping[str, Any]


@dataclass(frozen=True)
class JsonLogWriter:
    logs_dir: Path
    lock: Any
    redact_message: Callable[[str], str]
    cleanup_state: CleanupState
    retention_days: int = 7
    suppression_window_seconds: int = 60

    def write(self, level: str, module: str, message: str) -> None:
        try:
            self.logs_dir.mkdir(exist_ok=True, parents=True)
            now = time.time()
            date_str = time.strftime("%Y-%m-%d", time.localtime(now))
            log_file = self.logs_dir / f"{date_str}.json"
            redacted = self.redact_message(message)
            entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                "level": level,
                "module": module,
                "message": redacted,
            }
            with self.lock:
                digest = hashlib.sha256(f"{level}\0{module}\0{redacted}".encode("utf-8")).hexdigest()
                prefix = f"log_suppression:{digest}:"
                first_at = float(self.cleanup_state.get(prefix + "first_at", 0.0) or 0.0)
                count = int(self.cleanup_state.get(prefix + "count", 0) or 0)
                if first_at and now - first_at < max(1, self.suppression_window_seconds):
                    self.cleanup_state[prefix + "count"] = count + 1
                    self.cleanup_state[prefix + "last_at"] = now
                    return
                with open(log_file, "a", encoding="utf-8") as file:
                    if count:
                        summary = {
                            "timestamp": entry["timestamp"],
                            "level": level,
                            "module": module,
                            "message": f"上一条相同日志在抑制窗口内重复 {count} 次。",
                            "event_type": "duplicate_summary",
                            "suppressed_count": count,
                            "first_seen_at": first_at,
                            "last_seen_at": float(self.cleanup_state.get(prefix + "last_at", first_at) or first_at),
                        }
                        file.write(json.dumps(summary, ensure_ascii=False) + "\n")
                    file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self.cleanup_state[prefix + "first_at"] = now
                self.cleanup_state[prefix + "last_at"] = now
                self.cleanup_state[prefix + "count"] = 0
            cleanup_json_logs(
                self.logs_dir,
                self.lock,
                self.cleanup_state,
                now=now,
                retention_days=self.retention_days,
            )
        except Exception as exc:
            print(f"[日志错误] 写入 JSON 日志失败: {exc}", flush=True)


def cleanup_json_logs(
    logs_dir: Path,
    lock: Any,
    cleanup_state: CleanupState,
    *,
    now: float | None = None,
    retention_days: int = 7,
) -> None:
    current_time = time.time() if now is None else now
    with lock:
        if current_time - cleanup_state.get("last_cleanup_time", 0.0) < 3600:
            return
        cleanup_state["last_cleanup_time"] = current_time

    try:
        retention_seconds = max(1, min(int(retention_days), 90)) * 24 * 60 * 60
        today_str = time.strftime("%Y-%m-%d", time.localtime(current_time))
        today_time = time.mktime(time.strptime(today_str, "%Y-%m-%d"))
        deleted: list[str] = []
        for path in logs_dir.glob("*.json"):
            match = re.match(r"^(\d{4}-\d{2}-\d{2})\.json$", path.name)
            if match:
                date_str = match.group(1)
                try:
                    file_time = time.mktime(time.strptime(date_str, "%Y-%m-%d"))
                    if today_time - file_time >= retention_seconds:
                        with lock:
                            path.unlink()
                        deleted.append(path.name)
                except Exception:
                    if current_time - path.stat().st_mtime > retention_seconds:
                        with lock:
                            path.unlink()
                        deleted.append(path.name)
        if deleted:
            deleted.sort()
            print(
                f"[清理] 已删除 {len(deleted)} 个过期 JSON 日志文件，"
                f"日期范围 {deleted[0]} 至 {deleted[-1]}，当前保留 {max(1, min(int(retention_days), 90))} 天。",
                flush=True,
            )
    except Exception as exc:
        print(f"[清理错误] 清理旧日志失败: {exc}", flush=True)
