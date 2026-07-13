from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class LoginAttemptLimiter:
    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, client_ip: str) -> bool:
        now = self._clock()
        cutoff = now - self.window_seconds
        key = client_ip or "unknown"
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                return False
            attempts.append(now)
            return True

    def reset(self, client_ip: str) -> None:
        with self._lock:
            self._attempts.pop(client_ip or "unknown", None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()
