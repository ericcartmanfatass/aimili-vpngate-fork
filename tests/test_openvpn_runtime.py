from __future__ import annotations

import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from aimilivpn.system.openvpn_runtime import OpenVPNRuntimeFacade, SIGKILL, SIGTERM


SAFE_CONFIG = """client
dev tun
proto tcp
remote 203.0.113.10 443
nobind
persist-key
persist-tun
verb 3
"""


def build_facade(root: Path, **overrides: object) -> OpenVPNRuntimeFacade:
    kwargs = {
        "openvpn_cmd": "openvpn",
        "auth_file": root / "auth.txt",
        "data_dir": root,
        "config_dir": root / "configs",
        "upstream_proxy_auth_path": root / "upstream_proxy_auth.txt",
        "get_upstream_proxy": lambda: (None, None, None),
        "write_upstream_proxy_auth_file": lambda: None,
        "run_command": lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="", stderr=""),
        "proc_root": root / "proc",
        "platform": "linux",
        "current_pid": lambda: 999,
        "kill_process": lambda pid, sig: None,
        "sleep": lambda seconds: None,
        "print_line": lambda message: None,
    }
    kwargs.update(overrides)
    return OpenVPNRuntimeFacade(**kwargs)  # type: ignore[arg-type]


class FakeOpenVPNProcess:
    def __init__(self, output: str) -> None:
        self.stdout = StringIO(output)
        self.terminated = False
        self.killed = False

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True


class OpenVPNRuntimeFacadeTests(unittest.TestCase):
    def test_get_version_parses_and_caches_openvpn_version(self) -> None:
        calls: list[list[str]] = []

        def run_command(command: list[str], **kwargs: object) -> object:
            calls.append(command)
            return SimpleNamespace(stdout="OpenVPN 2.6.8 x86_64", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp), run_command=run_command)

            self.assertEqual(facade.get_version(), 2.6)
            self.assertEqual(facade.get_version(), 2.6)
            self.assertEqual(len(calls), 1)

    def test_get_version_falls_back_to_legacy_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(
                Path(tmp),
                run_command=lambda *args, **kwargs: SimpleNamespace(stdout="", stderr=""),
            )

            self.assertEqual(facade.get_version(), 2.4)

    def test_command_includes_upstream_proxy_for_tcp_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "node.ovpn"
            config_path.write_text(SAFE_CONFIG, encoding="utf-8")
            facade = build_facade(
                root,
                get_upstream_proxy=lambda: ("socks", "127.0.0.1", 1080),
                write_upstream_proxy_auth_file=lambda: str(root / "proxy-auth.txt"),
                run_command=lambda *args, **kwargs: SimpleNamespace(stdout="OpenVPN 2.5.0", stderr=""),
            )

            command = facade.command(str(config_path), route_nopull=True, dev="tun9")

            self.assertIn("--socks-proxy", command)
            self.assertIn("127.0.0.1", command)
            self.assertIn("1080", command)
            self.assertIn(str(root / "proxy-auth.txt"), command)
            self.assertIn("--route-nopull", command)

    def test_kill_existing_processes_terminates_matching_openvpn_processes(self) -> None:
        killed: list[tuple[int, int]] = []
        messages: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc_root = root / "proc"
            proc_root.mkdir()
            matching = proc_root / "101"
            matching.mkdir()
            matching.joinpath("cmdline").write_bytes(
                b"openvpn\0--config\0" + str(root / "configs" / "node.ovpn").encode("utf-8") + b"\0"
            )
            other = proc_root / "102"
            other.mkdir()
            other.joinpath("cmdline").write_bytes(b"python\0script.py\0")
            current = proc_root / "999"
            current.mkdir()
            current.joinpath("cmdline").write_bytes(
                b"openvpn\0--config\0" + str(root / "configs" / "current.ovpn").encode("utf-8") + b"\0"
            )
            facade = build_facade(
                root,
                proc_root=proc_root,
                kill_process=lambda pid, sig: killed.append((pid, sig)),
                print_line=lambda message: messages.append(message),
            )

            facade.kill_existing_processes()

            self.assertEqual(killed, [(101, SIGTERM), (101, SIGKILL)])
            self.assertTrue(any("101" in message for message in messages))

    def test_kill_existing_processes_skips_non_linux(self) -> None:
        killed: list[tuple[int, int]] = []
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp), platform="win32", kill_process=lambda pid, sig: killed.append((pid, sig)))

            facade.kill_existing_processes()

            self.assertEqual(killed, [])

    def test_run_until_ready_wires_runtime_callbacks_and_command(self) -> None:
        process = FakeOpenVPNProcess("notice\nInitialization Sequence Completed\n")
        logs: list[tuple[str, str]] = []
        statuses: list[str] = []
        commands: list[list[str]] = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "node.ovpn"
            config_path.write_text(SAFE_CONFIG, encoding="utf-8")
            facade = build_facade(
                root,
                run_command=lambda *args, **kwargs: SimpleNamespace(stdout="OpenVPN 2.5.0", stderr=""),
            )

            ok, message, returned = facade.run_until_ready(
                config_file=str(config_path),
                keep_alive=True,
                route_nopull=True,
                timeout=2,
                dev="tun9",
                cwd=root,
                log_line=lambda level, line: logs.append((level, line)),
                status_callback=lambda line: statuses.append(line),
                popen_factory=lambda command, *args, **kwargs: (commands.append(command) or process),  # type: ignore[arg-type]
            )

            self.assertTrue(ok)
            self.assertIn("OpenVPN connected", message)
            self.assertIs(returned, process)
            self.assertFalse(process.terminated)
            self.assertIn("--config", commands[0])
            self.assertIn(str(config_path), commands[0])
            self.assertIn("--route-nopull", commands[0])
            self.assertTrue(any("Initialization Sequence Completed" in line for _, line in logs))
            self.assertIn("initialization sequence completed", statuses)


if __name__ == "__main__":
    unittest.main()
