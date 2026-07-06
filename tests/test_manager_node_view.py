from __future__ import annotations

import unittest
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_node_view import ManagerNodeViewRuntime


class ManagerNodeViewRuntimeTests(unittest.TestCase):
    def make_runtime(self, allowed_countries: set[str] | None = None) -> ManagerNodeViewRuntime:
        allowed = {"JP"} if allowed_countries is None else allowed_countries
        return ManagerNodeViewRuntime(
            allowed_countries=Mock(name="allowed_countries", return_value=allowed),
            active_node_id=Mock(name="active_node_id", return_value="jp_1"),
            parse_int=Mock(name="parse_int"),
        )

    def test_node_matches_when_no_allowed_country_limit(self) -> None:
        runtime = self.make_runtime(set())

        self.assertTrue(runtime.node_matches_allowed_countries({"country_short": "US"}))

    def test_node_matches_country_short_or_id_prefix(self) -> None:
        runtime = self.make_runtime({"JP", "US"})

        self.assertTrue(runtime.node_matches_allowed_countries({"country_short": "jp"}))
        self.assertTrue(runtime.node_matches_allowed_countries({"id": "US_node_1"}))
        self.assertFalse(runtime.node_matches_allowed_countries({"country_short": "KR", "id": "KR_node_1"}))

    def test_sort_all_nodes_delegates_to_core_sort(self) -> None:
        runtime = self.make_runtime()
        nodes = [{"id": "n1"}]

        with patch("aimilivpn.system.manager_node_view.sort_nodes_for_display", return_value=sentinel.sorted_nodes) as sort:
            result = runtime.sort_all_nodes(nodes)

        self.assertIs(result, sentinel.sorted_nodes)
        sort.assert_called_once_with(nodes, parse_int=runtime.parse_int)

    def test_context_active_node_id_uses_state_callback(self) -> None:
        runtime = self.make_runtime()

        self.assertEqual(runtime.context_active_node_id(), "jp_1")
        runtime.active_node_id.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
