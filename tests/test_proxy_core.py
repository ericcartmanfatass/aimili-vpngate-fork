from __future__ import annotations

import subprocess
import unittest

from aimilivpn.core.proxy import check_proxy_health, curl_check_ip, parse_curl_ip_output, proxy_probe_hosts


class ProxyCoreTests(unittest.TestCase):
    def test_proxy_probe_hosts_formats_bind_addresses(self) -> None:
        self.assertEqual(proxy_probe_hosts("::"), ["[::1]", "127.0.0.1"])
        self.assertEqual(proxy_probe_hosts("0.0.0.0"), ["127.0.0.1"])
        self.assertEqual(proxy_probe_hosts("2001:db8::1"), ["[2001:db8::1]", "127.0.0.1"])
        self.assertEqual(proxy_probe_hosts("127.0.0.1"), ["127.0.0.1"])

    def test_parse_curl_ip_output(self) -> None:
        self.assertEqual(
            parse_curl_ip_output(0, "198.51.100.10\n0.123 200"),
            {"ok": True, "ip": "198.51.100.10", "latency_ms": 123},
        )
        self.assertIsNone(parse_curl_ip_output(7, ""))
        self.assertIsNone(parse_curl_ip_output(0, "198.51.100.10\n0.123 500"))

    def test_curl_check_ip_adds_proxy_credentials(self) -> None:
        commands: list[list[str]] = []

        def run_command(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="203.0.113.1\n0.050 200", stderr="")

        result = curl_check_ip(
            "http://ip.example",
            proxy_host="127.0.0.1",
            proxy_port=7928,
            get_proxy_credentials=lambda: ("user", "pass"),
            run_command=run_command,
        )

        self.assertEqual(result, {"ok": True, "ip": "203.0.113.1", "latency_ms": 50})
        self.assertIn("--proxy-user", commands[0])
        self.assertIn("user:pass", commands[0])

    def test_check_proxy_health_reports_local_proxy_failure(self) -> None:
        result = check_proxy_health(
            proxy_host="127.0.0.1",
            proxy_port=7928,
            tun_dev="tun0",
            is_linux=False,
            get_proxy_credentials=lambda: (None, None),
            diagnose_local_obstructions=lambda port, host: (False, "not listening"),
            connect_tcp=lambda host, port, timeout: (_ for _ in ()).throw(OSError("refused")),
        )

        self.assertFalse(result["ok"])
        self.assertIn("not listening", result["error"])

    def test_check_proxy_health_reports_missing_tun(self) -> None:
        result = check_proxy_health(
            proxy_host="127.0.0.1",
            proxy_port=7928,
            tun_dev="tun9",
            is_linux=True,
            get_proxy_credentials=lambda: (None, None),
            diagnose_local_obstructions=lambda port, host: None,
            connect_tcp=lambda host, port, timeout: None,
            tun_exists=lambda dev: False,
        )

        self.assertFalse(result["ok"])
        self.assertIn("ERR_ROUTE_DEV_NOT_FOUND", result["error"])

    def test_check_proxy_health_returns_curl_result(self) -> None:
        def run_command(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, stdout="203.0.113.2\n0.040 200", stderr="")

        result = check_proxy_health(
            proxy_host="127.0.0.1",
            proxy_port=7928,
            tun_dev="tun0",
            is_linux=False,
            get_proxy_credentials=lambda: (None, None),
            diagnose_local_obstructions=lambda port, host: None,
            connect_tcp=lambda host, port, timeout: None,
            run_command=run_command,
        )

        self.assertEqual(result, {"ok": True, "ip": "203.0.113.2", "latency_ms": 40})


if __name__ == "__main__":
    unittest.main()
