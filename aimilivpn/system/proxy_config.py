from __future__ import annotations

import os
import threading
from typing import Any


def parse_positive_int(value: str | None, default: int) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default


def parse_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


MAX_PROXY_CONNECTIONS = parse_positive_int(os.environ.get("LOCAL_PROXY_MAX_CONNECTIONS"), 256)
proxy_connection_sem = threading.BoundedSemaphore(MAX_PROXY_CONNECTIONS)
RELAY_IDLE_TIMEOUT_SECONDS = parse_positive_int(os.environ.get("LOCAL_PROXY_RELAY_IDLE_TIMEOUT_SECONDS"), 120)
_BIND_DEV = os.environ.get("TUN_DEV", "tun0").encode("utf-8")


def set_bind_device(bind_dev: str) -> None:
    global _BIND_DEV
    _BIND_DEV = (bind_dev or "tun0").encode("utf-8")


def bind_device_bytes() -> bytes:
    return _BIND_DEV


def bind_device_name() -> str:
    return _BIND_DEV.decode("utf-8", errors="replace")
