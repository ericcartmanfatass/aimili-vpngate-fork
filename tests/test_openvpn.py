from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path

from aimilivpn.core.openvpn import (
    openvpn_command,
    run_openvpn_until_ready,
    split_openvpn_command,
    stop_process,
    write_ovpn_config,
)
from aimilivpn.core.security import UnsafeOpenVPNConfig


SAFE_CONFIG = """client
dev tun
proto tcp
remote 203.0.113.10 443
nobind
persist-key
persist-tun
verb 3
"""


class FakeProcess:
    def __init__(self) -> None:
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


class FakeOpenVPNProcess(FakeProcess):
    def __init__(self, output: str) -> None:
        super().__init__()
        self.stdout = StringIO(output)


class OpenVPNHelperTests(unittest.TestCase):
    def test_split_openvpn_command_accepts_args(self) -> None:
        self.assertEqual(split_openvpn_command("openvpn --suppress-timestamps"), ["openvpn", "--suppress-timestamps"])

    def test_openvpn_command_builds_expected_flags(self) -> None:
        command = openvpn_command(
            "openvpn",
            "/tmp/node.ovpn",
            auth_file="/tmp/auth.txt",
            route_nopull=True,
            dev="tun9",
            openvpn_version=2.5,
            config_text=SAFE_CONFIG,
            upstream_proxy=("socks", "127.0.0.1", 1080),
            upstream_proxy_auth_file="/tmp/proxy-auth.txt",
            capath="/etc/ssl/certs",
        )

        self.assertIn("--config", command)
        self.assertIn("/tmp/node.ovpn", command)
        self.assertIn("--auth-user-pass", command)
        self.assertIn("/tmp/auth.txt", command)
        self.assertIn("--route-nopull", command)
        self.assertIn("--dev", command)
        self.assertIn("tun9", command)
        self.assertIn("--data-ciphers", command)
        self.assertIn("--socks-proxy", command)
        self.assertIn("/tmp/proxy-auth.txt", command)

    def test_openvpn_command_uses_ncp_ciphers_for_old_openvpn(self) -> None:
        command = openvpn_command(
            "openvpn",
            "/tmp/node.ovpn",
            auth_file="/tmp/auth.txt",
            route_nopull=False,
            dev="tun0",
            openvpn_version=2.4,
        )

        self.assertIn("--ncp-ciphers", command)
        self.assertNotIn("--route-nopull", command)

    def test_write_ovpn_config_sanitizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "node.ovpn"
            write_ovpn_config(path, SAFE_CONFIG)

            self.assertEqual(path.read_text(encoding="utf-8"), SAFE_CONFIG)

    def test_write_ovpn_config_rejects_unsafe_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UnsafeOpenVPNConfig):
                write_ovpn_config(Path(tmp) / "node.ovpn", SAFE_CONFIG + "script-security 2\n")

    def test_stop_process_terminates_running_process(self) -> None:
        process = FakeProcess()

        stop_process(process)  # type: ignore[arg-type]

        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)

    def test_run_openvpn_until_ready_detects_success(self) -> None:
        process = FakeOpenVPNProcess("notice\nInitialization Sequence Completed\n")
        logs: list[tuple[str, str]] = []

        ok, message, returned = run_openvpn_until_ready(
            config_file="/tmp/node.ovpn",
            keep_alive=True,
            route_nopull=True,
            timeout=2,
            dev="tun9",
            command_builder=lambda config_file, route_nopull, dev: ["openvpn", "--config", config_file, "--dev", dev],
            cwd="/tmp",
            log_line=lambda level, line: logs.append((level, line)),
            popen_factory=lambda *args, **kwargs: process,  # type: ignore[arg-type]
        )

        self.assertTrue(ok)
        self.assertIn("OpenVPN connected", message)
        self.assertIs(returned, process)
        self.assertFalse(process.terminated)
        self.assertTrue(any("Initialization Sequence Completed" in line for _, line in logs))

    def test_run_openvpn_until_ready_stops_failed_process_and_diagnoses(self) -> None:
        process = FakeOpenVPNProcess("fatal error\n")

        ok, message, returned = run_openvpn_until_ready(
            config_file="/tmp/node.ovpn",
            keep_alive=False,
            route_nopull=True,
            timeout=2,
            dev="tun9",
            command_builder=lambda config_file, route_nopull, dev: ["openvpn"],
            cwd="/tmp",
            diagnose_failure=lambda tail: (2002, f"bad tail={tail[-1]}"),
            popen_factory=lambda *args, **kwargs: process,  # type: ignore[arg-type]
        )

        self.assertFalse(ok)
        self.assertIn("bad tail=fatal error", message)
        self.assertIsNone(returned)
        self.assertTrue(process.terminated)


if __name__ == "__main__":
    unittest.main()
