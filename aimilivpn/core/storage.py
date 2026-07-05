from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .models import QualityResult, RegionProfile, VpnNode, node_from_dict, node_to_dict
from .regions import normalized_region


class JsonStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def read(self, path: Path, default: Any) -> Any:
        with self._lock:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return default

    def write(self, path: Path, data: Any) -> None:
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp, path)
            try:
                path.chmod(0o600)
            except OSError:
                pass


class NodeRepository:
    def __init__(self, path: Path, store: JsonStore | None = None) -> None:
        self.path = path
        self.store = store or JsonStore()

    def list_nodes(self, filters: dict[str, Any] | None = None) -> list[VpnNode]:
        items = self.store.read(self.path, [])
        nodes = [node_from_dict(item) for item in items if isinstance(item, dict)]
        if not filters:
            return nodes
        country = filters.get("country_code")
        if country:
            nodes = [node for node in nodes if (node.country_code or "").upper() == str(country).upper()]
        return nodes

    def get(self, node_id: str) -> VpnNode | None:
        return next((node for node in self.list_nodes() if node.id == node_id), None)

    def list_node_dicts(self) -> list[dict[str, Any]]:
        """Return legacy node dictionaries without dropping unknown fields."""
        items = self.store.read(self.path, [])
        if not isinstance(items, list):
            return []
        return [dict(item) for item in items if isinstance(item, dict)]

    def replace_all_dicts(self, nodes: list[dict[str, Any]]) -> None:
        """Persist legacy node dictionaries during the gradual migration."""
        clean_nodes = [dict(node) for node in nodes if isinstance(node, dict)]
        self.store.write(self.path, clean_nodes)

    def upsert_many_dicts(self, nodes: list[dict[str, Any]]) -> None:
        existing = {str(node.get("id") or ""): node for node in self.list_node_dicts() if node.get("id")}
        for node in nodes:
            node_id = str(node.get("id") or "")
            if node_id:
                existing[node_id] = dict(node)
        self.store.write(self.path, list(existing.values()))

    def upsert_many(self, nodes: list[VpnNode]) -> None:
        existing = {node.id: node for node in self.list_nodes()}
        for node in nodes:
            existing[node.id] = node
        self.store.write(self.path, [node_to_dict(node) for node in existing.values()])

    def update_node(self, node_id: str, patch: dict[str, Any]) -> None:
        items = [node_to_dict(node) for node in self.list_nodes()]
        for item in items:
            if item.get("id") == node_id:
                item.update(patch)
                self.store.write(self.path, items)
                return
        raise KeyError(node_id)


class RegionRepository:
    def __init__(self, path: Path, store: JsonStore | None = None) -> None:
        self.path = path
        self.store = store or JsonStore()

    def list_regions(self) -> list[RegionProfile]:
        items = self.store.read(self.path, [])
        return [RegionProfile(**item) for item in items if isinstance(item, dict)]

    def get(self, region_id: str) -> RegionProfile | None:
        return next((region for region in self.list_regions() if region.id == region_id), None)

    def create(self, region: RegionProfile) -> None:
        region = normalized_region(region)
        if self.get(region.id):
            raise ValueError(f"region already exists: {region.id}")
        regions = self.list_regions()
        regions.append(region)
        self.store.write(self.path, [region.__dict__ for region in regions])

    def update(self, region_id: str, patch: dict[str, Any]) -> None:
        regions = [region.__dict__ for region in self.list_regions()]
        for region in regions:
            if region.get("id") == region_id:
                region.update(patch)
                normalized = normalized_region(RegionProfile(**region))
                region.clear()
                region.update(normalized.__dict__)
                self.store.write(self.path, regions)
                return
        raise KeyError(region_id)

    def delete(self, region_id: str) -> None:
        regions = [region.__dict__ for region in self.list_regions()]
        remaining = [region for region in regions if region.get("id") != region_id]
        if len(remaining) == len(regions):
            raise KeyError(region_id)
        self.store.write(self.path, remaining)


class QualityRepository:
    def __init__(self, path: Path, store: JsonStore | None = None) -> None:
        self.path = path
        self.store = store or JsonStore()

    def save(self, result: QualityResult) -> None:
        items = self.store.read(self.path, [])
        if not isinstance(items, list):
            items = []
        items.append(result.__dict__)
        self.store.write(self.path, items)

    def latest_for_node(self, node_id: str) -> QualityResult | None:
        latest = self.list_latest().get(node_id)
        return latest

    def list_latest(self) -> dict[str, QualityResult]:
        items = self.store.read(self.path, [])
        latest: dict[str, QualityResult] = {}
        if not isinstance(items, list):
            return latest
        for item in items:
            if not isinstance(item, dict):
                continue
            result = QualityResult(**item)
            if result.node_id:
                latest[result.node_id] = result
        return latest


class SettingsRepository:
    def __init__(self, path: Path, store: JsonStore | None = None) -> None:
        self.path = path
        self.store = store or JsonStore()

    def get(self, key: str, default: Any = None) -> Any:
        data = self.store.read(self.path, {})
        return data.get(key, default) if isinstance(data, dict) else default

    def set(self, key: str, value: Any) -> None:
        data = self.store.read(self.path, {})
        if not isinstance(data, dict):
            data = {}
        data[key] = value
        self.store.write(self.path, data)
