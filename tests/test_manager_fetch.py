from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
