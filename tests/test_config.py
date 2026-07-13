from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aimilivpn.core.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_scamalytics_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "VPNGATE_DATA_DIR": tmp,
                "SCAMALYTICS_USERNAME": "user",
                "SCAMALYTICS_API_KEY": "secret-key",
                "SCAMALYTICS_TIMEOUT_SECONDS": "12",
                "SCAMALYTICS_CACHE_TTL_SECONDS": "120",
                "SCAMALYTICS_RATE_LIMIT_PER_MINUTE": "9",
                "SCAMALYTICS_API_URL": "https://example.test/{username}/",
            }
            with patch.dict(os.environ, env, clear=False):
                config = load_config(Path(tmp))

        self.assertTrue(config.scamalytics_configured)
        self.assertEqual(config.scamalytics_username, "user")
        self.assertEqual(config.scamalytics_api_key, "secret-key")
        self.assertEqual(config.scamalytics_timeout_seconds, 12)
        self.assertEqual(config.scamalytics_cache_ttl_seconds, 120)
        self.assertEqual(config.scamalytics_rate_limit_per_minute, 9)
        self.assertEqual(config.scamalytics_api_url, "https://example.test/{username}/")

    def test_load_config_marks_scamalytics_unconfigured_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "VPNGATE_DATA_DIR": tmp,
                "SCAMALYTICS_USERNAME": "user",
                "SCAMALYTICS_API_KEY": "",
            }
            with patch.dict(os.environ, env, clear=False):
                config = load_config(Path(tmp))

        self.assertFalse(config.scamalytics_configured)

    def test_load_config_defaults_blank_runtime_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                "VPNGATE_DATA_DIR": "   ",
                "LOCAL_PROXY_HOST": "   ",
                "UI_HOST": "   ",
                "OPENVPN_CMD": "   ",
                "LOCAL_PROXY_PORT": " 9000 ",
                "ALLOW_INSECURE_FETCH": " yes ",
                "VPNGATE_API_URL": "   ",
                "SCAMALYTICS_API_URL": "   ",
            }
            with patch.dict(os.environ, env, clear=True):
                config = load_config(root)

        self.assertEqual(config.data_dir, root / "vpngate_data")
        self.assertEqual(config.local_proxy_host, "127.0.0.1")
        self.assertEqual(config.ui_host, "127.0.0.1")
        self.assertEqual(config.openvpn_cmd, "openvpn")
        self.assertEqual(config.local_proxy_port, 9000)
        self.assertTrue(config.allow_insecure_fetch)
        self.assertEqual(config.api_url, "https://www.vpngate.net/api/iphone/")
        self.assertEqual(config.scamalytics_api_url, "https://api11.scamalytics.com/{username}/")

    def test_load_config_resolves_default_data_dir_from_root(self) -> None:
        root = Path("relative-root")

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(root)

        self.assertEqual(config.data_dir, root.resolve() / "vpngate_data")
        self.assertEqual(config.config_dir, root.resolve() / "vpngate_data" / "configs")
        self.assertEqual(config.blacklist_file, root.resolve() / "vpngate_data" / "blacklist.json")
        self.assertEqual(config.regions_file, root.resolve() / "vpngate_data" / "regions.json")
        self.assertEqual(config.quality_results_file, root.resolve() / "vpngate_data" / "quality_results.json")
        self.assertEqual(config.settings_file, root.resolve() / "vpngate_data" / "settings.json")
        self.assertFalse(config.trust_proxy_headers)
        self.assertEqual(config.trusted_proxy_addresses, ("127.0.0.1", "::1"))


if __name__ == "__main__":
    unittest.main()
