from __future__ import annotations

import unittest

from aimilivpn.core.models import QualityResult, RegionProfile, VpnNode
from aimilivpn.core.regions import (
    InvalidRegion,
    match_node,
    normalized_region,
    preview_region,
    region_from_mapping,
    validate_region,
)


def region(**updates: object) -> RegionProfile:
    data = {
        "id": "asia-low-risk",
        "name": "Asia Low Risk",
        "country_codes": ["jp", "KR"],
        "include_keywords": [],
        "exclude_keywords": [],
        "min_quality_score": None,
        "max_risk_score": None,
        "enabled": True,
    }
    data.update(updates)
    return RegionProfile(**data)  # type: ignore[arg-type]


class RegionsTests(unittest.TestCase):
    def test_validate_region_accepts_basic_profile(self) -> None:
        validate_region(region())

    def test_validate_region_rejects_bad_id(self) -> None:
        with self.assertRaises(InvalidRegion):
            validate_region(region(id="Bad_ID"))

    def test_normalized_region_uppercases_country_codes(self) -> None:
        normalized = normalized_region(region(country_codes=["jp", "kr", "JP"]))

        self.assertEqual(normalized.country_codes, ["JP", "KR"])

    def test_region_from_mapping_parses_form_like_values(self) -> None:
        parsed = region_from_mapping({
            "id": "jp-fast",
            "name": "Japan Fast",
            "country_codes": "jp, kr",
            "include_keywords": "tokyo, seoul",
            "exclude_keywords": "hosting",
            "min_quality_score": "70",
            "max_risk_score": "30",
            "enabled": "false",
        })

        self.assertEqual(parsed.country_codes, ["jp", "kr"])
        self.assertEqual(parsed.include_keywords, ["tokyo", "seoul"])
        self.assertEqual(parsed.exclude_keywords, ["hosting"])
        self.assertEqual(parsed.min_quality_score, 70)
        self.assertEqual(parsed.max_risk_score, 30)
        self.assertFalse(parsed.enabled)

    def test_match_node_supports_vpn_node(self) -> None:
        node = VpnNode(
            id="jp_1",
            source="vpngate",
            country="Japan",
            country_code="JP",
            ip="203.0.113.1",
            port=1194,
            proto="udp",
            hostname="tokyo.example",
        )

        self.assertTrue(match_node(region(), node))

    def test_match_node_supports_legacy_dict_and_keywords(self) -> None:
        node = {
            "id": "jp_1",
            "country_short": "JP",
            "country": "Japan",
            "host_name": "tokyo-fast",
            "owner": "Example ISP",
        }

        self.assertTrue(match_node(region(include_keywords=["tokyo"]), node))
        self.assertFalse(match_node(region(include_keywords=["osaka"]), node))
        self.assertFalse(match_node(region(exclude_keywords=["example isp"]), node))

    def test_match_node_applies_quality_and_risk(self) -> None:
        node = {"id": "jp_1", "country_short": "JP", "score": 80}
        quality = QualityResult(
            node_id="jp_1",
            exit_ip="203.0.113.1",
            tcp_latency_ms=50,
            openvpn_success=True,
            handshake_ms=1000,
            risk_provider="test",
            risk_score=30,
            risk_level="low",
            proxy_detected=False,
            datacenter_detected=False,
            country_match=True,
            checked_at="2026-06-17T00:00:00Z",
            score=80,
        )

        self.assertTrue(match_node(region(min_quality_score=70, max_risk_score=40), node, quality))
        self.assertFalse(match_node(region(min_quality_score=90), node, quality))
        self.assertFalse(match_node(region(max_risk_score=20), node, quality))

    def test_preview_region_counts_matches(self) -> None:
        nodes = [
            {"id": "jp_1", "country_short": "JP", "host_name": "tokyo"},
            {"id": "us_1", "country_short": "US", "host_name": "new-york"},
            {"id": "kr_1", "country_short": "KR", "host_name": "seoul"},
        ]

        preview = preview_region(region(include_keywords=["o"]), nodes)

        self.assertEqual(preview.total_nodes, 3)
        self.assertEqual(preview.matched_nodes, 2)
        self.assertEqual(preview.matched_node_ids, ["jp_1", "kr_1"])
        self.assertEqual(preview.exclusion_reasons, {"country_not_allowed": 1})

    def test_quality_rules_reject_untested_nodes_with_stable_reason(self) -> None:
        preview = preview_region(
            region(min_quality_score=70, max_risk_score=40),
            [{"id": "jp_1", "country_short": "JP", "score": 9999}],
        )

        self.assertEqual(preview.matched_nodes, 0)
        self.assertEqual(preview.exclusion_reasons, {"quality_not_tested": 1})


if __name__ == "__main__":
    unittest.main()
