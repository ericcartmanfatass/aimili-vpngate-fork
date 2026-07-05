from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any


DaemonTask = tuple[Callable[..., Any], tuple[Any, ...]]


def format_proxy_url(host: str, port: int) -> str:
    host_part = f"[{host}]" if ":" in host else host
    return f"http://{host_part}:{port}"


def build_initial_state(
    *,
    api_url: str,
    instance_id: str,
    tun_dev: str,
    policy_table: str,
    allowed_countries: Iterable[str],
    target_valid_nodes: int,
    fetch_interval_seconds: int,
    check_interval_seconds: int,
    local_proxy_host: str,
    local_proxy_port: int,
    last_check_message: str,
    active_node_latency: str,
) -> dict[str, Any]:
    return {
        "api_url": api_url,
        "instance_id": instance_id,
        "tun_dev": tun_dev,
        "policy_table": policy_table,
        "allowed_countries": sorted(allowed_countries),
        "target_valid_nodes": target_valid_nodes,
        "fetch_interval_seconds": fetch_interval_seconds,
        "check_interval_seconds": check_interval_seconds,
        "local_proxy": format_proxy_url(local_proxy_host, local_proxy_port),
        "active_openvpn_node_id": "",
        "last_fetch_status": "starting",
        "last_check_message": last_check_message,
        "is_connecting": True,
        "active_node_latency": active_node_latency,
        "blacklisted_nodes": 0,
    }


def start_daemon_threads(tasks: Iterable[DaemonTask]) -> None:
    for target, args in tasks:
        threading.Thread(target=target, args=args, daemon=True).start()


def wait_for_gateway(
    host: str,
    port: int,
    *,
    attempts: int = 30,
    delay_seconds: float = 0.5,
    timeout_seconds: float = 0.5,
    socket_factory: Callable[[int, int], Any] = socket.socket,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    is_ipv6 = ":" in host
    address_family = socket.AF_INET6 if is_ipv6 else socket.AF_INET
    connect_host = _connect_host(host, is_ipv6)

    for _ in range(attempts):
        sock = None
        try:
            sock = socket_factory(address_family, socket.SOCK_STREAM)
            sock.settimeout(timeout_seconds)
            try:
                sock.connect((connect_host, port))
                return True
            except Exception:
                if connect_host == "::1" and _try_ipv4_loopback(socket_factory, port, timeout_seconds):
                    return True
                raise
        except Exception:
            sleep(delay_seconds)
        finally:
            if sock is not None:
                _close_socket(sock)
    return False


def _connect_host(host: str, is_ipv6: bool) -> str:
    if host in ("::", "0.0.0.0", ""):
        return "::1" if is_ipv6 else "127.0.0.1"
    return host


def _try_ipv4_loopback(
    socket_factory: Callable[[int, int], Any],
    port: int,
    timeout_seconds: float,
) -> bool:
    sock = None
    try:
        sock = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_seconds)
        sock.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        if sock is not None:
            _close_socket(sock)


def _close_socket(sock: Any) -> None:
    try:
        sock.close()
    except Exception:
        pass
