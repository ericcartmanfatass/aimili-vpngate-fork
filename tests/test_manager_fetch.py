from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system.manager_fetch import ManagerFetchRuntime


class ManagerFetchRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerFetchRuntime:
        return ManagerFetchRuntime(
            api_url="https://example.test/api",
            config_dir=Path("configs"),
            max_scan_rows=100,
            allowed_countries={"JP"},
            allow_insecure_fetch=False,
            blacklist_file=Path("blacklist.json"),
            lock=sentinel.lock,
            invalid_backoff_seconds=30,
            read_nodes=Mock(name="read_nodes", return_value=[{"id": "jp_1"}]),
            set_state=Mock(name="set_state"),
            log_line=Mock(name="log_line"),
            diagnose_api_failure=Mock(name="diagnose_api_failure"),
            get_upstream_proxy=Mock(name="get_upstream_proxy"),
            get_upstream_proxy_auth=Mock(name="get_upstream_proxy_auth"),
            country_translations={"Japan": "Japan"},
            safe_name=Mock(name="safe_name"),
            now=Mock(name="now", return_value=123.0),
        )

    def test_blacklist_store_uses_configured_dependencies(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_fetch.BlacklistStore", return_value=sentinel.store) as store_cls:
            store = runtime.blacklist_store()

        self.assertIs(store, sentinel.store)
        store_cls.assert_called_once_with(
            path=Path("blacklist.json"),
            lock=sentinel.lock,
            backoff_seconds=30,
            now=runtime.now,
        )

    def test_facade_wires_fetch_dependencies(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_fetch.VpnGateFetchFacade", return_value=sentinel.facade) as facade_cls:
            facade = runtime.facade()

        self.assertIs(facade, sentinel.facade)
        kwargs = facade_cls.call_args.kwargs
        self.assertEqual(kwargs["api_url"], "https://example.test/api")
        self.assertEqual(kwargs["config_dir"], Path("configs"))
        self.assertIs(kwargs["load_blacklist"].__self__, runtime)
        self.assertIs(kwargs["load_blacklist"].__func__, ManagerFetchRuntime.load_blacklist)
        self.assertIs(kwargs["cached_nodes"].__self__, runtime)
        self.assertIs(kwargs["cached_nodes"].__func__, ManagerFetchRuntime.cached_nodes)
        self.assertIs(kwargs["set_state"], runtime.set_state)
        self.assertIs(kwargs["log_line"], runtime.log_line)
        self.assertIs(kwargs["now"], runtime.now)

    def test_fetch_wrappers_delegate_to_facade(self) -> None:
        runtime = self.make_runtime()
        facade = Mock()
        facade.fetch_api_text_via_proxy.return_value = "proxy-body"
        facade.fetch_api_text.return_value = "direct-body"
        facade.fetch_candidates.return_value = [{"id": "jp_1"}]

        with patch.object(runtime, "facade", return_value=facade):
            self.assertEqual(
                runtime.fetch_api_text_via_proxy("url", "http", "127.0.0.1", 8080, False),
                "proxy-body",
            )
            self.assertEqual(runtime.fetch_api_text("url", False), "direct-body")
            self.assertEqual(runtime.fetch_candidates(), [{"id": "jp_1"}])

        facade.fetch_api_text_via_proxy.assert_called_once_with("url", "http", "127.0.0.1", 8080, False)
        facade.fetch_api_text.assert_called_once_with("url", False)
        facade.fetch_candidates.assert_called_once_with()

    def test_configured_global_mode_never_falls_back_to_instance_vpngate_request(self) -> None:
        runtime = self.make_runtime()
        runtime.global_nodes_file = Path("missing-global-nodes.json")
        facade = Mock()
        with patch.object(runtime, "facade", return_value=facade):
            candidates = runtime.fetch_candidates()

        self.assertEqual(candidates, [])
        facade.fetch_candidates.assert_not_called()
        self.assertTrue(any(call.kwargs.get("last_fetch_status") == "empty" for call in runtime.set_state.call_args_list))

    def test_global_empty_snapshot_uses_persistent_instance_backoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime()
            runtime.global_nodes_file = Path(tmp) / "nodes.json"
            now = [100.0]
            state = [{}]
            runtime.now = lambda: now[0]
            runtime.get_state = lambda: state[-1]
            runtime.global_retry_backoff_seconds = (60, 300)

            self.assertEqual(runtime.fetch_candidates(), [])
            first_updates = runtime.set_state.call_args_list
            first_retry = next(call.kwargs["global_next_retry_at"] for call in first_updates if "global_next_retry_at" in call.kwargs)
            self.assertEqual(first_retry, 160.0)

            state.append({"global_fetch_failure_count": 1, "global_next_retry_at": 160.0})
            now[0] = 120.0
            self.assertEqual(runtime.fetch_candidates(), [])
            self.assertEqual(runtime.set_state.call_args_list[-1].kwargs["last_fetch_status"], "backoff")

    def test_global_snapshot_candidates_are_filtered_without_network_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_file = root / "jp-1.ovpn"
            config_file.write_text("client\n", encoding="utf-8")
            (root / "nodes.json").write_text(json.dumps({"nodes": [
                {"id": "jp-1", "server_ip": "203.0.113.1", "country_short": "JP", "config_file": str(config_file)},
                {"id": "us-1", "server_ip": "203.0.113.2", "country_short": "US", "config_file": str(config_file)},
            ]}), encoding="utf-8")
            runtime = self.make_runtime()
            runtime.global_nodes_file = root / "nodes.json"

            candidates = runtime.fetch_candidates()

        self.assertEqual([item["id"] for item in candidates], ["jp-1"])


if __name__ == "__main__":
    unittest.main()
