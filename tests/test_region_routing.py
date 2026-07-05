from __future__ import annotations

import importlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from aimilivpn.core.models import RegionProfile


def load_manager(data_dir: str):
    os.environ["VPNGATE_DATA_DIR"] = data_dir
    with redirect_stdout(io.StringIO()):
        if "vpngate_manager" in sys.modules:
            return importlib.reload(sys.modules["vpngate_manager"])
        return importlib.import_module("vpngate_manager")


class RegionRoutingTests(unittest.TestCase):
    def test_region_target_filters_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)
            manager.REGION_REPOSITORY.create(
                RegionProfile(
                    id="asia-fast",
                    name="Asia Fast",
                    country_codes=["JP", "KR"],
                    include_keywords=["tokyo"],
                )
            )

            nodes = [
                {"id": "jp_1", "country_short": "JP", "host_name": "tokyo-fast"},
                {"id": "kr_1", "country_short": "KR", "host_name": "seoul"},
                {"id": "us_1", "country_short": "US", "host_name": "new-york"},
            ]

            filtered = manager.filter_nodes_by_routing_region(nodes, "region:asia-fast")

            self.assertEqual([node["id"] for node in filtered], ["jp_1"])

    def test_legacy_country_target_still_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)

            self.assertTrue(manager.node_matches_routing_region({"country": "Japan"}, "Japan"))
            self.assertTrue(manager.node_matches_routing_region({"country_short": "JP"}, "JP"))
            self.assertTrue(manager.node_matches_routing_region({"country": "Japan"}, "country:Japan"))


if __name__ == "__main__":
    unittest.main()
