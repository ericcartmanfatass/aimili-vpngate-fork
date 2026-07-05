from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Any, Callable

ProxyCredentials = Callable[[], tuple[str | None, str | None]]
DiagnoseLocal = Callable[[int, str], tuple[bool, str] | None]
ConnectTcp = Callable[[str, int, float], None]
RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def proxy_probe_hosts(proxy_host: str) -> list[str]:
    if proxy_host == "::":
        return ["[::1]", "127.0.0.1"]
    if proxy_host in ("0.0.0.0", ""):
        return ["127.0.0.1"]
    if ":" in proxy_host:
        return [f"[{proxy_host}]", "127.0.0.1"]
    return [proxy_host]


def check_proxy_health(
    *,
    proxy_host: str,
    proxy_port: int,
    tun_dev: str,
    is_linux: bool,
    get_proxy_credentials: ProxyCredentials,
    diagnose_local_obstructions: DiagnoseLocal,
    connect_tcp: ConnectTcp | None = None,
    tun_exists: Callable[[str], bool] | None = None,
    run_command: RunCommand = subprocess.run,
    ip_urls: tuple[str, ...] = ("http://ip.sb", "http://api.ipify.org"),
) -> dict[str, Any]:
    connect_tcp = connect_tcp or _connect_tcp
    tun_exists = tun_exists or (lambda dev: Path(f"/sys/class/net/{dev}").exists())

    try:
        _assert_proxy_listening(proxy_host, proxy_port, connect_tcp, timeout=1.5)
    except Exception as exc:
        diag = diagnose_local_obstructions(proxy_port, proxy_host)
        diag_msg = diag[1] if diag else f"port {proxy_port} connection failed: {exc}"
        return {"ok": False, "error": f"proxy service is not running ({diag_msg})"}

    if is_linux and not tun_exists(tun_dev):
        return {
            "ok": False,
            "error": f"[ERR_ROUTE_DEV_NOT_FOUND] VPN tunnel device ({tun_dev}) is not available",
        }

    try:
        for url in ip_urls:
            result = curl_check_ip(
                url,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                get_proxy_credentials=get_proxy_credentials,
                run_command=run_command,
            )
            if result:
                return result

        try:
            _assert_proxy_listening(proxy_host, proxy_port, connect_tcp, timeout=1.0)
        except Exception:
            diag = diagnose_local_obstructions(proxy_port, proxy_host)
            if diag:
                return {"ok": False, "error": f"exit connectivity test failed | local diagnostic: {diag[1]}"}

        return {
            "ok": False,
            "error": "exit connectivity test failed (ip.sb and api.ipify.org are unreachable through the local proxy)",
        }
    except Exception as exc:
        return {"ok": False, "error": f"exit connectivity test raised an exception: {exc}"}


def curl_check_ip(
    url: str,
    *,
    proxy_host: str,
    proxy_port: int,
    get_proxy_credentials: ProxyCredentials,
    run_command: RunCommand = subprocess.run,
) -> dict[str, Any] | None:
    for host in proxy_probe_hosts(proxy_host):
        proxy_url = f"socks5h://{host}:{proxy_port}"
        proxy_user, proxy_pass = get_proxy_credentials()
        command = [
            "curl",
            "-s",
            "-w",
            "\n%{time_total} %{http_code}",
            "-x",
            proxy_url,
            url,
            "--max-time",
            "5",
        ]
        if proxy_user is not None and proxy_pass is not None:
            command.extend(["--proxy-user", f"{proxy_user}:{proxy_pass}"])
        try:
            result = run_command(command, capture_output=True, text=True, timeout=6)
            parsed = parse_curl_ip_output(result.returncode, result.stdout)
            if parsed:
                return parsed
        except Exception:
            pass
    return None


def parse_curl_ip_output(returncode: int, stdout: str) -> dict[str, Any] | None:
    if returncode != 0:
        return None
    lines = stdout.strip().splitlines()
    if len(lines) < 2:
        return None
    ip = lines[0].strip()
    time_info = lines[1].strip().split()
    if len(time_info) != 2:
        return None
    total_time, http_code = time_info
    if http_code != "200" or not ip:
        return None
    return {"ok": True, "ip": ip, "latency_ms": int(float(total_time) * 1000)}


def _assert_proxy_listening(proxy_host: str, proxy_port: int, connect_tcp: ConnectTcp, *, timeout: float) -> None:
    connect_host = proxy_host
    is_ipv6 = ":" in proxy_host
    if connect_host in ("::", "0.0.0.0", ""):
        connect_host = "::1" if is_ipv6 else "127.0.0.1"
    try:
        connect_tcp(connect_host, proxy_port, timeout)
    except Exception:
        if connect_host == "::1":
            connect_tcp("127.0.0.1", proxy_port, timeout)
        else:
            raise


def _connect_tcp(host: str, port: int, timeout: float) -> None:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect((host, port))
    finally:
        sock.close()
