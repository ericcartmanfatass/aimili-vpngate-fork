from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aimilivpn.system.vpngate_fetch import VpnGateFetchFacade


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def sample_api_text(ip: str = "203.0.113.1", country: str = "JP") -> str:
    config = base64.b64encode(
        f"client\nproto tcp\nremote {ip} 443\n".encode("utf-8")
    ).decode("ascii")
    header = [
        "#HostName",
        "IP",
        "Score",
        "Ping",
        "Speed",
        "CountryLong",
        "CountryShort",
        "NumVpnSessions",
        "OpenVPN_ConfigData_Base64",
    ]
    row = [
        "tokyo",
        ip,
        "100",
        "20",
        "1000",
        "Japan",
        country,
        "3",
        config,
    ]
    return ",".join(header) + "\n" + ",".join(row) + "\n"


def build_facade(root: Path, **overrides: object) -> VpnGateFetchFacade:
    states: list[dict[str, object]] = overrides.pop("states", [])  # type: ignore[assignment]
    logs: list[tuple[str, str]] = overrides.pop("logs", [])  # type: ignore[assignment]
    kwargs = {
        "api_url": "https://example.test/api",
        "config_dir": root,
        "max_scan_rows": 100,
        "allowed_countries": {"JP"},
        "allow_insecure_fetch": False,
        "load_blacklist": lambda: {},
        "cached_nodes": lambda: [],
        "set_state": lambda **update: states.append(update),
        "log_line": lambda level, message: logs.append((level, message)),
        "diagnose_api_failure": lambda url: ("1001", "diagnostic"),
        "get_upstream_proxy": lambda: ("", "", 0),
        "get_upstream_proxy_auth": lambda: (None, None),
        "country_translations": {"Japan": "日本"},
        "safe_name": lambda value: value.replace(".", "_"),
        "country_catalog_file": root / "country_catalog.json",
        "sleep": lambda seconds: None,
        "now": lambda: 100.0,
        "urlopen": lambda *args, **kwargs: FakeResponse(sample_api_text().encode("utf-8")),
    }
    kwargs.update(overrides)
    return VpnGateFetchFacade(**kwargs)  # type: ignore[arg-type]


class VpnGateFetchFacadeTests(unittest.TestCase):
    def test_fetch_api_text_reads_with_direct_urlopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(
                Path(tmp),
                urlopen=lambda *args, **kwargs: FakeResponse(b"api-body"),
            )

            self.assertEqual(facade.fetch_api_text(), "api-body")

    def test_fetch_api_text_falls_back_when_proxy_fails(self) -> None:
        logs: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(
                Path(tmp),
                logs=logs,
                get_upstream_proxy=lambda: ("http", "127.0.0.1", 8080),
                urlopen=lambda *args, **kwargs: FakeResponse(b"direct"),
            )

            with patch("builtins.print"):
                with patch.object(VpnGateFetchFacade, "fetch_api_text_via_proxy", side_effect=OSError("proxy down")):
                    self.assertEqual(facade.fetch_api_text(), "direct")

            self.assertEqual(logs[0][0], "WARNING")
            self.assertIn("使用上游 http 代理获取 API 失败", logs[0][1])
            self.assertIn("OSError", logs[0][1])
            self.assertNotIn("proxy down", logs[0][1])

    def test_fetch_candidates_parses_nodes_and_sets_success_state(self) -> None:
        states: list[dict[str, object]] = []
        logs: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp), states=states, logs=logs)

            with patch("builtins.print"):
                nodes = facade.fetch_candidates()

            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["country"], "日本")
            self.assertEqual(nodes[0]["remote_port"], 443)
            self.assertEqual(states[-1]["last_fetch_status"], "ok")
            self.assertTrue(any(level == "INFO" for level, _ in logs))
            catalog = json.loads((Path(tmp) / "country_catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(catalog["countries"][0]["country"], "JP")
            self.assertEqual(catalog["countries"][0]["node_count"], 1)

    def test_country_catalog_scans_the_complete_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = build_facade(root, max_scan_rows=1)
            first = sample_api_text("203.0.113.1", "JP").splitlines()
            second = sample_api_text("203.0.113.2", "DE").splitlines()

            facade._write_country_catalog("\n".join([first[0], first[1], second[1]]) + "\n")

            catalog = json.loads((root / "country_catalog.json").read_text(encoding="utf-8"))
            self.assertEqual({item["country"] for item in catalog["countries"]}, {"DE", "JP"})

    def test_fetch_candidates_records_diagnostic_on_failure(self) -> None:
        states: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(
                Path(tmp),
                states=states,
                urlopen=lambda *args, **kwargs: FakeResponse(b"bad data"),
            )

            with patch("builtins.print"):
                with self.assertRaises(RuntimeError):
                    facade.fetch_candidates()

            self.assertEqual(states[-1]["last_fetch_status"], "error")
            self.assertEqual(states[-1]["last_fetch_error_code"], "1001")


if __name__ == "__main__":
    unittest.main()
