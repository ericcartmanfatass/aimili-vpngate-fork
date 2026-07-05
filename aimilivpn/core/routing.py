from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(command: list[str], *, check: bool = False, timeout: float = 2, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        timeout=timeout,
        capture_output=capture_output,
        text=True,
    )


def cleanup_route_commands(table: str) -> list[list[str]]:
    table = str(table)
    return [
        ["ip", "rule", "del", "table", table],
        ["ip", "route", "flush", "table", table],
    ]


def policy_route_commands(interface: str, table: str) -> list[list[str]]:
    interface = str(interface)
    table = str(table)
    return [
        ["ip", "route", "add", "default", "dev", interface, "table", table],
        ["ip", "rule", "add", "oif", interface, "table", table],
    ]


def rp_filter_commands(interface: str, value: int = 2) -> list[list[str]]:
    value_text = str(value)
    return [
        ["sysctl", "-w", f"net.ipv4.conf.{target}.rp_filter={value_text}"]
        for target in ["all", "default", str(interface)]
    ]


def format_route_error(exc: BaseException | None = None, *, table: str = "100") -> str:
    detail = f": {exc}" if exc else ""
    return (
        f"[ERR_ROUTE_TABLE_ADD_FAILED] Failed to configure policy routing table {table}{detail}. "
        "Check iproute2 availability and root/CAP_NET_ADMIN permissions."
    )


def classify_route_error(exc: BaseException) -> str:
    message = str(exc).lower()
    if isinstance(exc, FileNotFoundError) or "no such file" in message:
        return "command_not_found"
    if "permission" in message or "operation not permitted" in message:
        return "permission_denied"
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout"
    return "failed"

