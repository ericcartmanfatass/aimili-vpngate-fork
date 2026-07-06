from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from aimilivpn.core.nodes import sort_nodes_for_display


@dataclass
class ManagerNodeViewRuntime:
    allowed_countries: Callable[[], Iterable[str]]
    active_node_id: Callable[[], str]
    parse_int: Callable[[Any], int]

    def node_matches_allowed_countries(self, node: dict[str, Any]) -> bool:
        allowed_countries = set(self.allowed_countries())
        if not allowed_countries:
            return True
        country_short = str(node.get("country_short") or "").strip().upper()
        if country_short in allowed_countries:
            return True
        node_id = str(node.get("id") or "").strip().upper()
        return any(node_id.startswith(f"{country}_") for country in allowed_countries)

    def sort_all_nodes(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sort_nodes_for_display(nodes, parse_int=self.parse_int)

    def context_active_node_id(self) -> str:
        return self.active_node_id()
