from __future__ import annotations

from pathlib import Path
import unittest

from aimilivpn.core.config import AppConfig
from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.web.api import quality_provider_status, quality_to_dict, region_to_dict


class WebApiHelperTests(unittest.TestCase):
    def test_region_to_dict_maps_region_profile(self) -> None:
        region = RegionProfile(
            id="jp-tokyo",
            name="Japan Tokyo",
            country_codes=["JP"],
            include_keywords=["tokyo"],
            exclude_keywords=["slow"],
            min_quality_score=70,
            max_risk_score=30,
            enabled=True,
        )

        payload = region_to_dict(region)

        self.assertEqual(payload["id"], "jp-tokyo")
        self.assertEqual(payload["country_codes"], ["JP"])
        self.assertEqual(payload["include_keywords"], ["tokyo"])
        self.assertEqual(payload["exclude_keywords"], ["slow"])
        self.assertEqual(payload["min_quality_score"], 70)
        self.assertEqual(payload["max_risk_score"], 30)
        self.assertTrue(payload["enabled"])

    def test_quality_to_dict_excludes_raw_response(self) -> None:
        result = QualityResult(
            node_id="jp_1",
            exit_ip="203.0.113.1",
            tcp_latency_ms=80,
            openvpn_success=True,
            handshake_ms=3000,
            risk_provider="scamalytics",
            risk_score=12,
            risk_level="low",
            proxy_detected=False,
            datacenter_detected=False,
            country_match=True,
            checked_at="2026-06-17T00:00:00Z",
            raw_response={"api_key": "secret"},
            score=94,
            label="Excellent",
            reasons=["tcp reachable"],
        )

        payload = quality_to_dict(result)

        self.assertNotIn("raw_response", payload)
        self.assertEqual(payload["risk_provider"], "scamalytics")
        self.assertEqual(payload["score"], 94)
        self.assertEqual(payload["reasons"], ["tcp reachable"])

    def test_quality_provider_status_hides_scamalytics_credentials(self) -> None:
        config = AppConfig(
            data_dir=Path("/tmp/data"),
            config_dir=Path("/tmp/data/configs"),
            nodes_file=Path("/tmp/data/nodes.json"),
            state_file=Path("/tmp/data/state.json"),
            auth_file=Path("/tmp/data/auth.txt"),
            local_proxy_host="127.0.0.1",
            local_proxy_port=7928,
            ui_host="::",
            ui_port=8787,
            openvpn_cmd="openvpn",
            tun_dev="tun0",
            policy_table="100",
            allowed_countries=set(),
            allow_insecure_fetch=False,
            scamalytics_username="demo-user",
            scamalytics_api_key="super-secret",
            scamalytics_timeout_seconds=11,
            scamalytics_cache_ttl_seconds=120,
            scamalytics_rate_limit_per_minute=7,
        )

        status = quality_provider_status(config)

        providers = {item["name"]: item for item in status["providers"]}
        self.assertTrue(providers["scamalytics"]["configured"])
        self.assertEqual(providers["scamalytics"]["timeout_seconds"], 11)
        self.assertEqual(providers["scamalytics"]["cache_ttl_seconds"], 120)
        self.assertEqual(providers["scamalytics"]["rate_limit_per_minute"], 7)
        self.assertNotIn("api_key", providers["scamalytics"])
        self.assertNotIn("username", providers["scamalytics"])
        self.assertNotIn("super-secret", str(status))


if __name__ == "__main__":
    unittest.main()
