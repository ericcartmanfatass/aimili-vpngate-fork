from __future__ import annotations

import re
import unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_wiring import (
    ConnectionRuntimeWiring,
    EntryRuntimeWiring,
    FetchRuntimeWiring,
    JsonLogRuntimeWiring,
    MonitoringRuntimeWiring,
    NodeProbeRuntimeWiring,
    NodeViewRuntimeWiring,
    OpenVPNRuntimeWiring,
    ProxyHealthRuntimeWiring,
    QualityRuntimeWiring,
    RepositoryRuntimeWiring,
    RuntimeFilesWiring,
    RuntimeStateWiring,
    ServiceRuntimeWiring,
    ThreadRuntimeWiring,
    UiRuntimeWiring,
    WebManagerRuntimeWiring,
    apply_saved_ui_overrides,
    build_auth_runtime,
    build_connection_runtime,
    build_entry_runtime,
    build_fetch_runtime,
    build_json_log_runtime,
    build_monitoring_runtime,
    build_node_probe_runtime,
    build_node_view_runtime,
    build_openvpn_runtime,
    build_proxy_health_runtime,
    build_quality_runtime,
    build_repository_runtime,
    build_runtime_files,
    build_runtime_state,
    build_repositories,
    build_service_runtime,
    build_shared_state,
    build_thread_runtime,
    build_ui_runtime,
    build_web_runtime,
)
from aimilivpn.system.manager_runtime_context import build_manager_runtime_context


REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGER_SOURCE = REPO_ROOT / "aimilivpn" / "system" / "vpngate_manager.py"


def make_wiring(wiring_cls):
    values = {field.name: Mock(name=field.name) for field in fields(wiring_cls)}
    return wiring_cls(**values)


RUNTIME_BUILD_CASES = (
    ("entry", EntryRuntimeWiring, "ManagerEntryRuntime", build_entry_runtime),
    ("connection", ConnectionRuntimeWiring, "ManagerConnectionRuntime", build_connection_runtime),
    ("repository", RepositoryRuntimeWiring, "ManagerRepositoryRuntime", build_repository_runtime),
    ("quality", QualityRuntimeWiring, "ManagerQualityRuntime", build_quality_runtime),
    ("fetch", FetchRuntimeWiring, "ManagerFetchRuntime", build_fetch_runtime),
    ("ui", UiRuntimeWiring, "ManagerUiRuntime", build_ui_runtime),
    ("runtime_state", RuntimeStateWiring, "ManagerRuntimeState", build_runtime_state),
    ("runtime_files", RuntimeFilesWiring, "ManagerRuntimeFiles", build_runtime_files),
    ("thread", ThreadRuntimeWiring, "ManagerThreadRuntime", build_thread_runtime),
    ("node_view", NodeViewRuntimeWiring, "ManagerNodeViewRuntime", build_node_view_runtime),
    ("proxy_health", ProxyHealthRuntimeWiring, "ManagerProxyHealthRuntime", build_proxy_health_runtime),
    ("json_log", JsonLogRuntimeWiring, "ManagerJsonLogRuntime", build_json_log_runtime),
    ("monitoring", MonitoringRuntimeWiring, "ManagerMonitoringRuntime", build_monitoring_runtime),
    ("service", ServiceRuntimeWiring, "ManagerServiceRuntime", build_service_runtime),
    ("openvpn", OpenVPNRuntimeWiring, "ManagerOpenVPNRuntime", build_openvpn_runtime),
    ("node_probe", NodeProbeRuntimeWiring, "ManagerNodeProbeRuntime", build_node_probe_runtime),
    ("web", WebManagerRuntimeWiring, "ManagerWebRuntime", build_web_runtime),
)


class ManagerWiringTests(unittest.TestCase):
    def test_vpngate_manager_keeps_construction_in_runtime_context(self) -> None:
        source = MANAGER_SOURCE.read_text(encoding="utf-8")

        self.assertIn("from aimilivpn.system import manager_runtime_context as runtime_context", source)

        forbidden_patterns = {
            "direct repository import": r"from aimilivpn\.core\.storage import .*Repository",
            "direct manager runtime import": r"from aimilivpn\.system\.manager_[a-z_]+ import Manager",
            "direct manager runtime construction": r"\bManager[A-Za-z]+Runtime\(",
            "direct manager state construction": r"\bManagerRuntime(State|Files)\(",
            "direct mutable state construction": r"\bManagerMutableState\(",
            "direct thread lock construction": r"\bthreading\.(RLock|Lock)\(",
            "direct repository construction": r"\b(NodeRepository|RegionRepository|QualityRepository)\(",
            "direct environment import": r"^import (os|sys)$",
            "direct wiring import": r"manager_wiring",
            "direct runtime wiring": r"\b[A-Za-z]+RuntimeWiring\(",
            "direct root resolution": r"\bresolve_manager_root_dir\(",
            "direct config loading": r"\bload_manager_runtime_config\(",
        }

        for label, pattern in forbidden_patterns.items():
            with self.subTest(label=label):
                self.assertIsNone(re.search(pattern, source, flags=re.MULTILINE))

    def test_manager_wiring_types_facade_stays_thin(self) -> None:
        source = (REPO_ROOT / "aimilivpn" / "system" / "manager_wiring_types.py").read_text(encoding="utf-8")

        self.assertNotIn("@dataclass", source)
        self.assertIn("manager_wiring_foundation_types", source)
        self.assertIn("manager_wiring_support_types", source)
        self.assertIn("manager_wiring_connection_types", source)
        self.assertIn("manager_wiring_web_types", source)
        self.assertIn("manager_wiring_process_types", source)

    def test_build_manager_runtime_context_uses_context_class(self) -> None:
        with patch(
            "aimilivpn.system.manager_runtime_context.ManagerRuntimeContext",
            return_value=sentinel.context,
        ) as context_cls:
            context = build_manager_runtime_context(compiled=True)

        self.assertIs(context, sentinel.context)
        context_cls.assert_called_once_with(compiled=True)

    def test_build_repositories_uses_runtime_paths(self) -> None:
        paths = SimpleNamespace(
            nodes_file=Path("nodes.json"),
            regions_file=Path("regions.json"),
            quality_results_file=Path("quality.json"),
        )

        with (
            patch(
                "aimilivpn.system.manager_wiring.NodeRepository",
                return_value=sentinel.node_repository,
            ) as node_cls,
            patch(
                "aimilivpn.system.manager_wiring.RegionRepository",
                return_value=sentinel.region_repository,
            ) as region_cls,
            patch(
                "aimilivpn.system.manager_wiring.QualityRepository",
                return_value=sentinel.quality_repository,
            ) as quality_cls,
        ):
            repositories = build_repositories(paths)

        self.assertIs(repositories.node_repository, sentinel.node_repository)
        self.assertIs(repositories.region_repository, sentinel.region_repository)
        self.assertIs(repositories.quality_repository, sentinel.quality_repository)
        node_cls.assert_called_once_with(Path("nodes.json"))
        region_cls.assert_called_once_with(Path("regions.json"))
        quality_cls.assert_called_once_with(Path("quality.json"))

    def test_build_shared_state_links_active_sessions_to_mutable_state(self) -> None:
        shared_state = build_shared_state()

        self.assertIs(shared_state.active_sessions, shared_state.mutable_state.active_sessions)
        self.assertTrue(hasattr(shared_state.lock, "acquire"))
        self.assertTrue(hasattr(shared_state.maintenance_lock, "locked"))

    def test_build_auth_runtime_uses_default_auth_runtime(self) -> None:
        with patch("aimilivpn.system.manager_wiring.ManagerAuthRuntime", return_value=sentinel.runtime) as runtime_cls:
            runtime = build_auth_runtime()

        self.assertIs(runtime, sentinel.runtime)
        runtime_cls.assert_called_once_with()

    def test_apply_saved_ui_overrides_uses_runtime_values(self) -> None:
        ui_runtime = Mock()
        ui_runtime.apply_saved_overrides.return_value = ("0.0.0.0", 9000, 9001)

        endpoints = apply_saved_ui_overrides(ui_runtime, "127.0.0.1", 8787, 7928)

        self.assertEqual(endpoints.ui_host, "0.0.0.0")
        self.assertEqual(endpoints.ui_port, 9000)
        self.assertEqual(endpoints.local_proxy_port, 9001)
        ui_runtime.apply_saved_overrides.assert_called_once_with()

    def test_apply_saved_ui_overrides_keeps_defaults_on_error(self) -> None:
        ui_runtime = Mock()
        ui_runtime.apply_saved_overrides.side_effect = ValueError("bad config")

        endpoints = apply_saved_ui_overrides(ui_runtime, "127.0.0.1", 8787, 7928)

        self.assertEqual(endpoints.ui_host, "127.0.0.1")
        self.assertEqual(endpoints.ui_port, 8787)
        self.assertEqual(endpoints.local_proxy_port, 7928)
        ui_runtime.apply_saved_overrides.assert_called_once_with()

    def test_build_runtime_passes_wiring_fields(self) -> None:
        for label, wiring_cls, runtime_name, build_runtime in RUNTIME_BUILD_CASES:
            with self.subTest(label=label):
                wiring = make_wiring(wiring_cls)

                with patch(
                    f"aimilivpn.system.manager_wiring.{runtime_name}",
                    return_value=sentinel.runtime,
                ) as runtime_cls:
                    runtime = build_runtime(wiring)

                self.assertIs(runtime, sentinel.runtime)
                runtime_cls.assert_called_once_with(**vars(wiring))


if __name__ == "__main__":
    unittest.main()
