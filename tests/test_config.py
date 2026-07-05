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


if __name__ == "__main__":
    unittest.main()
