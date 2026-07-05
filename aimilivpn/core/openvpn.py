from __future__ import annotations

import os
import queue
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from .security import sanitize_ovpn_config


def split_openvpn_command(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=(os.name != "nt")) or ["openvpn"]
    except ValueError as exc:
        raise RuntimeError(f"OPENVPN_CMD cannot be parsed: {exc}") from exc


def write_ovpn_config(path: Path, config_text: str) -> None:
    sanitized = sanitize_ovpn_config(config_text)
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(sanitized, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def openvpn_command(
    openvpn_cmd: str,
    config_file: Path | str,
    *,
    auth_file: Path | str,
    route_nopull: bool,
    dev: str,
    openvpn_version: float,
    config_text: str = "",
    upstream_proxy: tuple[str | None, str | None, int | None] = (None, None, None),
    upstream_proxy_auth_file: Path | str | None = None,
    capath: Path | str | None = None,
) -> list[str]:
    command = split_openvpn_command(openvpn_cmd)
    command.extend(
        [
            "--config",
            str(config_file),
            "--dev",
            dev,
            "--dev-type",
            "tun",
            "--pull-filter",
            "ignore",
            "route-ipv6",
            "--pull-filter",
            "ignore",
            "ifconfig-ipv6",
            "--route-delay",
            "2",
            "--connect-retry-max",
            "1",
            "--connect-timeout",
            "15",
            "--auth-user-pass",
            str(auth_file),
            "--auth-nocache",
        ]
    )

    if openvpn_version >= 2.5:
        command.extend(["--data-ciphers", "AES-128-CBC:AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305"])
    else:
        command.extend(["--ncp-ciphers", "AES-128-CBC:AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305"])

    command.extend(["--verb", "3"])

    if capath:
        command.extend(["--capath", str(capath)])

    if _is_config_tcp(config_text):
        ptype, host, port = upstream_proxy
        if ptype == "socks" and host and port:
            command.extend(["--socks-proxy", host, str(port)])
            if upstream_proxy_auth_file:
                command.append(str(upstream_proxy_auth_file))
        elif ptype == "http" and host and port:
            command.extend(["--http-proxy", host, str(port)])
            if upstream_proxy_auth_file:
                command.append(str(upstream_proxy_auth_file))

    if route_nopull:
        command.append("--route-nopull")
    return command


def stop_process(process: subprocess.Popen[str] | None, *, terminate_timeout: float = 8) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=terminate_timeout)
    except subprocess.TimeoutExpired:
        process.kill()


def run_openvpn_until_ready(
    *,
    config_file: str,
    keep_alive: bool,
    route_nopull: bool,
    timeout: int,
    dev: str,
    command_builder: Callable[[str, bool, str], list[str]],
    cwd: Path | str,
    stop_process_func: Callable[[subprocess.Popen[str] | None], None] = stop_process,
    diagnose_failure: Callable[[list[str]], tuple[int, str]] | None = None,
    log_line: Callable[[str, str], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
    print_line: Callable[[str], None] | None = None,
    popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> tuple[bool, str, subprocess.Popen[str] | None]:
    try:
        process = popen_factory(
            command_builder(config_file, route_nopull, dev),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd),
        )
    except FileNotFoundError:
        return False, "[ERR_OVPN_CMD_NOT_FOUND] openvpn command was not found", None
    except OSError as exc:
        return False, f"[ERR_OVPN_START_FAILED] openvpn failed to start: {exc}", None

    lines: queue.Queue[str | None] = queue.Queue()
    startup_done = [False]
    openvpn_logs: list[str] = []

    def emit_log(line: str) -> None:
        if log_line:
            log_line(_openvpn_log_level(line), f"[OpenVPN] {line}")

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            line_str = line.rstrip()
            if not startup_done[0]:
                openvpn_logs.append(line_str)
                lines.put(line_str)
            elif keep_alive:
                if print_line:
                    print_line(f"[OpenVPN] {line_str}")
                emit_log(line_str)
        if not startup_done[0]:
            lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    started = time.time()
    tail: list[str] = []
    ok = False
    message = "OpenVPN did not complete initialization."

    while time.time() - started < timeout:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        if line is None:
            break
        if line:
            tail.append(line)
            tail = tail[-50:]
            if keep_alive and print_line:
                print_line(f"[OpenVPN] {line}")
        lower = line.lower()
        if keep_alive and status_callback:
            status_callback(lower)
        if "initialization sequence completed" in lower:
            ok = True
            message = f"OpenVPN connected in {int((time.time() - started) * 1000)} ms."
            break
        if "auth_failed" in lower or "authentication failed" in lower:
            message = "AUTH_FAILED"
            break
        if "cannot ioctl" in lower or "fatal error" in lower:
            message = line[-220:]
            break
    else:
        message = f"OpenVPN timeout after {timeout}s."

    for line_str in openvpn_logs:
        emit_log(line_str)

    if not ok and diagnose_failure:
        err_code, diag_msg = diagnose_failure(tail)
        tail_text = tail[-1][-100:] if tail else "none"
        message = f"[error code {err_code}] {diag_msg} (tail: {tail_text})"

    startup_done[0] = True
    if not keep_alive or not ok:
        stop_process_func(process)
        process = None
    return ok, message, process


def _is_config_tcp(config_text: str) -> bool:
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        parts = line.split()
        if parts[0].lower() == "proto" and len(parts) >= 2 and "tcp" in parts[1].lower():
            return True
        if parts[0].lower() == "remote" and len(parts) >= 4 and "tcp" in parts[3].lower():
            return True
    return False


def _openvpn_log_level(line: str) -> str:
    line_lower = line.lower()
    if (
        "error" in line_lower
        or "failed" in line_lower
        or "cannot" in line_lower
        or "fatal" in line_lower
        or "permission denied" in line_lower
    ):
        return "ERROR"
    if "warning" in line_lower or "warn" in line_lower or "deprecated" in line_lower:
        return "WARNING"
    return "INFO"
