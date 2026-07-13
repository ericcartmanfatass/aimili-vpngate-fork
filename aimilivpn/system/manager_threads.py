from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from aimilivpn.system.startup import DaemonTask


@dataclass
class ManagerThreadRuntime:
    lock: Any
    maintenance_lock: Any
    maintain_valid_nodes: Callable[[bool], Any]
    on_thread_error: Callable[[str, BaseException], None] | None = None
    thread_factory: Callable[..., Any] = threading.Thread
    stop_event: threading.Event = field(default_factory=threading.Event)
    _threads: list[Any] = field(default_factory=list, init=False)
    _failures: list[tuple[str, BaseException]] = field(default_factory=list, init=False)
    _runtime_lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def run_with_lock(self, callback: Callable[[], Any]) -> Any:
        with self.lock:
            return callback()

    def try_acquire_maintenance_lock(self) -> bool:
        return self.maintenance_lock.acquire(blocking=False)

    def release_maintenance_lock(self) -> None:
        self.maintenance_lock.release()

    def _start(self, target: Callable[..., Any], args: tuple[Any, ...] = ()) -> Any:
        name = getattr(target, "__name__", target.__class__.__name__)

        def guarded_target() -> None:
            try:
                target(*args)
            except Exception as exc:
                with self._runtime_lock:
                    self._failures.append((name, exc))
                if self.on_thread_error is not None:
                    self.on_thread_error(name, exc)

        thread = self.thread_factory(target=guarded_target, daemon=True)
        with self._runtime_lock:
            self._threads.append(thread)
        thread.start()
        return thread

    def start_background_thread(self, target: Callable[[], Any]) -> None:
        self._start(target)

    def start_daemon_thread(self, target: Callable[..., Any], args: tuple[Any, ...]) -> None:
        self._start(target, args)

    def start_maintenance_thread(self) -> None:
        self._start(self.maintain_valid_nodes, (False,))

    def start_tasks(self, tasks: Iterable[DaemonTask]) -> None:
        for target, args in tasks:
            self._start(target, args)

    def stop_requested(self) -> bool:
        return self.stop_event.is_set()

    def wait(self, seconds: int | float) -> bool:
        return self.stop_event.wait(seconds)

    def failures(self) -> tuple[tuple[str, BaseException], ...]:
        with self._runtime_lock:
            return tuple(self._failures)

    def shutdown(self, timeout_seconds: float = 5.0) -> None:
        self.stop_event.set()
        current = threading.current_thread()
        with self._runtime_lock:
            threads = list(self._threads)
        for thread in threads:
            if thread is current:
                continue
            is_alive = getattr(thread, "is_alive", None)
            if not callable(is_alive) or is_alive():
                thread.join(timeout_seconds)
