from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import threading


@dataclass
class ManagerThreadRuntime:
    lock: Any
    maintenance_lock: Any
    maintain_valid_nodes: Callable[[bool], Any]
    thread_factory: Callable[..., Any] = threading.Thread

    def run_with_lock(self, callback: Callable[[], Any]) -> Any:
        with self.lock:
            return callback()

    def try_acquire_maintenance_lock(self) -> bool:
        return self.maintenance_lock.acquire(blocking=False)

    def release_maintenance_lock(self) -> None:
        self.maintenance_lock.release()

    def start_background_thread(self, target: Callable[[], Any]) -> None:
        self.thread_factory(target=target, daemon=True).start()

    def start_daemon_thread(self, target: Callable[..., Any], args: tuple[Any, ...]) -> None:
        self.thread_factory(target=target, args=args, daemon=True).start()

    def start_maintenance_thread(self) -> None:
        self.thread_factory(target=self.maintain_valid_nodes, args=(False,), daemon=True).start()
