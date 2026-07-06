from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system import quality_runtime
from aimilivpn.system.manager_quality import ManagerQualityRuntime


class ManagerQualityRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerQualityRuntime:
        return ManagerQualityRuntime(
            root_dir=Path("sample-root"),
            quality_repository=sentinel.quality_repository,
            region_repository=sentinel.region_repository,
            region_target_id=Mock(name="region_target_id"),
            read_nodes=Mock(name="read_nodes"),
            node_allowed=Mock(name="node_allowed"),
            bounded_int=Mock(name="bounded_int"),
            test_multiple_nodes=Mock(name="test_multiple_nodes"),
        )

    def test_get_scamalytics_provider_loads_config_and_caches_result(self) -> None:
        runtime = self.make_runtime()

        with (
            patch("aimilivpn.system.manager_quality.load_config", return_value=sentinel.config) as load_config,
            patch.object(
                quality_runtime,
                "configured_scamalytics_provider",
                return_value=sentinel.provider,
            ) as configured_provider,
        ):
            provider = runtime.get_scamalytics_provider()

        self.assertIs(provider, sentinel.provider)
        self.assertIs(runtime._scamalytics_provider, sentinel.provider)
        load_config.assert_called_once_with(Path("sample-root"))
        configured_provider.assert_called_once_with(sentinel.config, None)

    def test_record_quality_result_from_probe_uses_runtime_repository(self) -> None:
        runtime = self.make_runtime()
        provider_getter = Mock(name="provider_getter")
        node = {"id": "jp_1", "ip": "203.0.113.1"}

        with patch.object(quality_runtime, "record_from_probe", return_value=sentinel.result) as record_from_probe:
            result = runtime.record_quality_result_from_probe(
                node,
                True,
                80,
                "ok",
                provider_getter=provider_getter,
            )

        self.assertIs(result, sentinel.result)
        record_from_probe.assert_called_once_with(
            node,
            True,
            80,
            "ok",
            quality_repository=sentinel.quality_repository,
            provider_getter=provider_getter,
        )

    def test_check_quality_region_passes_manager_dependencies(self) -> None:
        runtime = self.make_runtime()

        with patch.object(quality_runtime, "check_region", return_value={"ok": True}) as check_region:
            result = runtime.check_quality_region("jp-region", limit=3)

        self.assertEqual(result, {"ok": True})
        check_region.assert_called_once_with(
            "jp-region",
            3,
            region_target_id=runtime.region_target_id,
            region_repository=sentinel.region_repository,
            quality_repository=sentinel.quality_repository,
            read_nodes=runtime.read_nodes,
            node_allowed=runtime.node_allowed,
            bounded_int=runtime.bounded_int,
            test_multiple_nodes=runtime.test_multiple_nodes,
        )

    def test_quality_provider_status_uses_root_dir(self) -> None:
        runtime = self.make_runtime()

        with patch.object(quality_runtime, "provider_status", return_value={"providers": []}) as provider_status:
            result = runtime.quality_provider_status()

        self.assertEqual(result, {"providers": []})
        provider_status.assert_called_once_with(Path("sample-root"))


if __name__ == "__main__":
    unittest.main()
