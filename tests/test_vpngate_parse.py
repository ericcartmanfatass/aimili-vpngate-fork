from __future__ import annotations

import base64
import unittest
from pathlib import Path

from aimilivpn.core.config import AppConfig
from aimilivpn.providers.vpngate import (
    country_catalog_from_text,
    decode_config,
    parse_legacy_candidates,
    parse_legacy_candidates_filtered,
    parse_vpngate_rows,
    row_to_legacy_node,
    row_to_node,
)


CONFIG = """client
dev tun
proto udp
remote 203.0.113.44 1194
resolv-retry infinite
nobind
persist-key
persist-tun
verb 3
"""


class VpngateProviderTests(unittest.TestCase):
    def test_parse_vpngate_rows_removes_hash_header(self) -> None:
        text = "#HostName,IP,CountryShort,CountryLong,Score,Ping,OpenVPN_ConfigData_Base64\nsrv,203.0.113.44,JP,Japan,10,32,abc\n"

        rows = parse_vpngate_rows(text)

        self.assertEqual(rows[0]["HostName"], "srv")
        self.assertEqual(rows[0]["CountryShort"], "JP")

    def test_country_catalog_uses_valid_unique_vpngate_nodes(self) -> None:
        encoded = base64.b64encode(CONFIG.encode("utf-8")).decode("ascii")
        text = (
            "#HostName,IP,CountryShort,CountryLong,OpenVPN_ConfigData_Base64\n"
            f"jp1,203.0.113.1,JP,Japan,{encoded}\n"
            f"jp2,203.0.113.1,JP,Japan,{encoded}\n"
            f"de1,203.0.113.2,DE,Germany,{encoded}\n"
            f"bad,203.0.113.3,INVALID,Invalid,{encoded}\n"
            "empty,203.0.113.4,FR,France,\n"
        )

        catalog = country_catalog_from_text(text, max_scan_rows=20)

        self.assertEqual(catalog, [
            {"country": "DE", "name": "Germany", "node_count": 1},
            {"country": "JP", "name": "Japan", "node_count": 1},
        ])

    def test_decode_config_sanitizes_base64(self) -> None:
        encoded = base64.b64encode(CONFIG.encode("utf-8")).decode("ascii")

        self.assertEqual(decode_config(encoded), CONFIG)

    def test_row_to_node_maps_remote_fields(self) -> None:
        node = row_to_node(
            {"HostName": "srv", "IP": "203.0.113.44", "CountryShort": "JP", "CountryLong": "Japan", "Score": "10", "Ping": "32"},
            CONFIG,
        )

        self.assertEqual(node.country_code, "JP")
        self.assertEqual(node.port, 1194)
        self.assertEqual(node.proto, "udp")

    def test_row_to_legacy_node_preserves_manager_fields(self) -> None:
        node = row_to_legacy_node(
            {
                "HostName": "srv",
                "IP": "203.0.113.44",
                "CountryShort": "JP",
                "CountryLong": "Japan",
                "Score": "10",
                "Ping": "32",
                "Speed": "2048",
                "NumVpnSessions": "3",
            },
            CONFIG,
            Path("/tmp/configs"),
            country_translations={"Japan": "Japan"},
        )

        self.assertEqual(node["country_short"], "JP")
        self.assertEqual(node["remote_port"], 1194)
        self.assertEqual(node["speed"], 2048)
        self.assertEqual(node["sessions"], 3)
        self.assertTrue(node["config_file"].endswith("JP_203.0.113.44_1194_udp.ovpn"))

    def test_parse_legacy_candidates_applies_country_filter(self) -> None:
        encoded = base64.b64encode(CONFIG.encode("utf-8")).decode("ascii")
        text = (
            "#HostName,IP,CountryShort,CountryLong,Score,Ping,Speed,NumVpnSessions,OpenVPN_ConfigData_Base64\n"
            f"srv,203.0.113.44,JP,Japan,10,32,2048,3,{encoded}\n"
        )
        config = AppConfig(
            data_dir=Path("/tmp"),
            config_dir=Path("/tmp/configs"),
            nodes_file=Path("/tmp/nodes.json"),
            state_file=Path("/tmp/state.json"),
            auth_file=Path("/tmp/auth.txt"),
            local_proxy_host="127.0.0.1",
            local_proxy_port=7928,
            ui_host="127.0.0.1",
            ui_port=8787,
            openvpn_cmd="openvpn",
            tun_dev="tun0",
            policy_table="100",
            allowed_countries={"KR"},
            allow_insecure_fetch=False,
        )

        self.assertEqual(parse_legacy_candidates(text, config, Path("/tmp/configs")), [])

    def test_parse_legacy_candidates_filtered_dedupes_and_skips_blacklist(self) -> None:
        encoded = base64.b64encode(CONFIG.encode("utf-8")).decode("ascii")
        text = (
            "#HostName,IP,CountryShort,CountryLong,Score,Ping,Speed,NumVpnSessions,OpenVPN_ConfigData_Base64\n"
            f"srv1,203.0.113.44,JP,Japan,10,32,2048,3,{encoded}\n"
            f"srv2,203.0.113.44,JP,Japan,20,12,2048,3,{encoded}\n"
            f"srv3,203.0.113.45,US,United States,20,12,2048,3,{encoded}\n"
        )

        nodes, seen, warnings = parse_legacy_candidates_filtered(
            text,
            Path("/tmp/configs"),
            max_scan_rows=10,
            allowed_countries={"JP"},
            blacklist={},
            now=100,
        )

        self.assertEqual([node["ip"] for node in nodes], ["203.0.113.44"])
        self.assertEqual(seen, {"203.0.113.44"})
        self.assertEqual(warnings, [])

        node_id = nodes[0]["id"]
        nodes, seen, warnings = parse_legacy_candidates_filtered(
            text,
            Path("/tmp/configs"),
            max_scan_rows=10,
            allowed_countries={"JP"},
            blacklist={node_id: {"until": 200}},
            seen_ips=set(),
            now=100,
        )

        self.assertEqual(nodes, [])
        self.assertEqual(seen, set())
        self.assertEqual(warnings, [])

    def test_parse_legacy_candidates_filtered_reports_invalid_rows(self) -> None:
        text = (
            "#HostName,IP,CountryShort,CountryLong,Score,Ping,Speed,NumVpnSessions,OpenVPN_ConfigData_Base64\n"
            "srv,203.0.113.44,JP,Japan,10,32,2048,3,not-valid-base64!!!\n"
        )

        nodes, seen, warnings = parse_legacy_candidates_filtered(
            text,
            Path("/tmp/configs"),
            max_scan_rows=10,
            allowed_countries={"JP"},
            blacklist={},
            now=100,
        )

        self.assertEqual(nodes, [])
        self.assertEqual(seen, set())
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
