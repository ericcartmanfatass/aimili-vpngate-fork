from __future__ import annotations

import unittest
from types import SimpleNamespace

from aimilivpn.web.api_contract import InvalidListQuery, canonical_route, contract_summary, parse_list_query


class ApiContractTests(unittest.TestCase):
    def test_contract_summary_exposes_stable_client_metadata(self) -> None:
        summary = contract_summary()

        self.assertEqual(summary["api_version"], "v1")
        self.assertIn("/api/v1/nodes", summary["resources"])
        self.assertEqual(summary["pagination"]["max_limit"], 500)
        self.assertEqual(summary["idempotency_header"], "X-Idempotency-Key")

    def test_v1_routes_map_to_compatible_handlers(self) -> None:
        self.assertEqual(canonical_route("GET", "/api/v1/nodes"), "/api/nodes")
        self.assertEqual(canonical_route("GET", "/api/v1/regions/jp"), "/api/regions/jp")
        self.assertEqual(canonical_route("POST", "/api/v1/operations/connect"), "/api/connect")
        self.assertEqual(canonical_route("PUT", "/api/v1/settings"), "/api/update_settings")

    def test_list_query_applies_bounded_pagination_and_filters(self) -> None:
        handler = SimpleNamespace(path="/api/v1/nodes?limit=25&offset=50&sort=latency&order=desc&country=JP")

        query = parse_list_query(
            handler,
            allowed_filters=("country",),
            allowed_sort=("id", "latency"),
            default_sort="id",
        )

        self.assertEqual(query.limit, 25)
        self.assertEqual(query.offset, 50)
        self.assertEqual(query.sort, "latency")
        self.assertEqual(query.order, "desc")
        self.assertEqual(query.filters, {"country": "JP"})

    def test_list_query_rejects_unknown_repeated_and_unbounded_values(self) -> None:
        cases = (
            "/api/v1/nodes?unknown=1",
            "/api/v1/nodes?limit=1&limit=2",
            "/api/v1/nodes?limit=999999",
            "/api/v1/nodes?sort=private_field",
        )
        for path in cases:
            with self.subTest(path=path), self.assertRaises(InvalidListQuery):
                parse_list_query(
                    SimpleNamespace(path=path),
                    allowed_sort=("id",),
                    default_sort="id",
                )


if __name__ == "__main__":
    unittest.main()
