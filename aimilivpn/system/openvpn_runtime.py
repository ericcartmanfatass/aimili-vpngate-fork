from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core import openvpn as openvpn_core

SIGTERM = getattr(signal, "SIGTERM", 15)
SIGKILL = getattr(signal, "SIGKILL", 9)


@dataclass
class OpenVPNRuntimeFacade:
    openvpn_cmd: str
    auth_file: Path
    data_dir: Path
    config_dir: Path
    upstream_proxy_auth_path: Path
    get_upstream_proxy: Callable[[], tuple[str | None, str | None, int | None]]
    write_upstream_proxy_auth_file: Callable[[], str | None]
    run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    proc_root: Path = Path("/proc")
    platform: str = sys.platform
    current_pid: Callable[[], int] = os.getpid
    kill_process: Callable[[int, int], None] = os.kill
    sleep: Callable[[float], None] = time.sleep
    print_line: Callable[[str], None] = print
    _openvpn_version: float | None = field(default=None, init=False)

    def split_command(self) -> list[str]:
        try:
            return openvpn_core.split_openvpn_command(self.openvpn_cmd)
        except RuntimeError as exc:
            raise RuntimeError(f"OPENVPN_CMD configuration cannot be parsed: {exc}") from exc

    def get_version(self) -> float:
        if self._openvpn_version is not None:
            return self._openvpn_version
        try:
            result = self.run_command(
                self.split_command() + ["--version"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            match = re.search(r"OpenVPN\s+(\d+\.\d+)", result.stdout or result.stderr)
            if match:
                self._openvpn_version = float(match.group(1))
                return self._openvpn_version
        except Exception:
            pass
        self._openvpn_version = 2.4
        return self._openvpn_version

    def command(self, config_file: str, route_nopull: bool, dev: str) -> list[str]:
        config_text = ""
        try:
            config_text = Path(config_file).read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

        capath = Path("/etc/ssl/certs") if Path("/etc/ssl/certs").exists() else None
        return openvpn_core.openvpn_command(
            self.openvpn_cmd,
            config_file,
            auth_file=self.auth_file,
            route_nopull=route_nopull,
            dev=dev,
            openvpn_version=self.get_version(),
            config_text=config_text,
            upstream_proxy=self.get_upstream_proxy(),
            upstream_proxy_auth_file=self.write_upstream_proxy_auth_file(),
            capath=capath,
        )

    def stop_process(self, process: subprocess.Popen[str] | None) -> None:
        openvpn_core.stop_process(process)

    def run_until_ready(
        self,
        *,
        config_file: str,
        keep_alive: bool,
        route_nopull: bool,
        timeout: int,
        dev: str,
        cwd: Path | str,
        diagnose_failure: Callable[[list[str]], tuple[int, str]] | None = None,
        log_line: Callable[[str, str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        print_line: Callable[[str], None] | None = None,
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> tuple[bool, str, subprocess.Popen[str] | None]:
        return openvpn_core.run_openvpn_until_ready(
            config_file=config_file,
            keep_alive=keep_alive,
            route_nopull=route_nopull,
            timeout=timeout,
            dev=dev,
            command_builder=self.command,
            cwd=cwd,
            stop_process_func=self.stop_process,
            diagnose_failure=diagnose_failure,
            log_line=log_line,
            status_callback=status_callback,
            print_line=print_line,
            popen_factory=popen_factory,
        )

    def kill_existing_processes(self) -> None:
        if not self.platform.startswith("linux"):
            return
        try:
            killed_pids: list[int] = []
            if not self.proc_root.exists():
                return
            own_markers = [
                str(self.data_dir),
                str(self.config_dir),
                str(self.auth_file),
                str(self.upstream_proxy_auth_path),
            ]
            for proc_dir in self.proc_root.iterdir():
                if not proc_dir.name.isdigit():
                    continue
                pid = int(proc_dir.name)
                if pid == self.current_pid():
                    continue
                cmdline = self._read_cmdline(proc_dir)
                if not cmdline:
                    continue
                args = cmdline.split()
                executable = Path(args[0]).name.lower() if args else ""
                if "openvpn" not in executable and "openvpn" not in cmdline.lower():
                    continue
                if any(marker and marker in cmdline for marker in own_markers):
                    try:
                        self.kill_process(pid, SIGTERM)
                        killed_pids.append(pid)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        self.print_line(f"[Cleanup] No permission to terminate OpenVPN PID {pid}")
            if killed_pids:
                self.sleep(0.5)
                for pid in killed_pids:
                    cmdline = self._read_cmdline(self.proc_root / str(pid))
                    if any(marker and marker in cmdline for marker in own_markers):
                        try:
                            self.kill_process(pid, SIGKILL)
                        except ProcessLookupError:
                            pass
                        except (OSError, PermissionError):
                            pass
                self.print_line(f"[Cleanup] Terminated AimiliVPN OpenVPN processes: {killed_pids}")
        except Exception as exc:
            self.print_line(f"[Cleanup Error] Failed to kill existing OpenVPN processes: {exc}")

    def _read_cmdline(self, proc_dir: Path) -> str:
        try:
            raw = (proc_dir / "cmdline").read_bytes()
        except OSError:
            return ""
        if not raw:
            return ""
        return " ".join(part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part)
