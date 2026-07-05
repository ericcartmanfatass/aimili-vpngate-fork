from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any, Callable


def probe_proxy_gateway(
    proxy_host: str,
    proxy_port: int,
    diagnose_local_obstructions: Callable[[int], tuple[bool, str] | None],
    *,
    timeout_seconds: float = 0.5,
    socket_factory: Callable[..., socket.socket] = socket.socket,
) -> tuple[bool, str]:
    proxy_ok = False
    proxy_err = ""
    is_ipv6 = ":" in proxy_host
    address_family = socket.AF_INET6 if is_ipv6 else socket.AF_INET
    sock = None
    try:
        sock = socket_factory(address_family, socket.SOCK_STREAM)
        sock.settimeout(timeout_seconds)
        connect_host = proxy_host
        if connect_host in ("::", "0.0.0.0", ""):
            connect_host = "::1" if is_ipv6 else "127.0.0.1"
        try:
            sock.connect((connect_host, proxy_port))
            proxy_ok = True
        except Exception:
            if connect_host == "::1":
                sock.close()
                sock = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout_seconds)
                sock.connect(("127.0.0.1", proxy_port))
                proxy_ok = True
            else:
                raise
    except Exception as exc:
        diag = diagnose_local_obstructions(proxy_port)
        proxy_err = diag[1] if diag else f"本地代理网关无法连接: {exc}"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    return proxy_ok, proxy_err


def read_json_log_entries(
    logs_dir: Path,
    *,
    date_str: str | None = None,
    lock: Any | None = None,
    on_error: Callable[[BaseException], None] | None = None,
) -> list[dict[str, Any]]:
    date_str = date_str or time.strftime("%Y-%m-%d", time.localtime())
    log_file = logs_dir / f"{date_str}.json"
    entries: list[dict[str, Any]] = []
    if not log_file.exists():
        return entries

    def read_entries() -> None:
        with open(log_file, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)

    try:
        if lock is None:
            read_entries()
        else:
            with lock:
                read_entries()
    except Exception as exc:
        if on_error is not None:
            on_error(exc)
    return entries
