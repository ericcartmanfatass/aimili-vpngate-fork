from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimilivpn.web.static_assets import get_static_asset, guess_content_type, is_safe_static_path


class StaticAssetsTests(unittest.TestCase):
    def test_safe_static_path_accepts_relative_assets(self) -> None:
        self.assertTrue(is_safe_static_path("app.js"))
        self.assertTrue(is_safe_static_path("nested/style.css"))

    def test_safe_static_path_rejects_absolute_and_traversal(self) -> None:
        self.assertFalse(is_safe_static_path("../secret.txt"))
        self.assertFalse(is_safe_static_path("/app.js"))
        self.assertFalse(is_safe_static_path(""))

    def test_guess_content_type(self) -> None:
        self.assertEqual(guess_content_type("style.css"), "text/css; charset=utf-8")
        self.assertEqual(guess_content_type("app.js"), "application/javascript; charset=utf-8")
        self.assertEqual(guess_content_type("icon.png"), "image/png")

    def test_get_static_asset_reads_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.js").write_bytes(b"console.log('ok')")

            self.assertEqual(get_static_asset("app.js", static_dir=root), b"console.log('ok')")

    def test_default_static_style_css_exists(self) -> None:
        css = get_static_asset("style.css")

        self.assertIsNotNone(css)
        self.assertIn(b":root", css or b"")

    def test_default_static_app_js_exists(self) -> None:
        js = get_static_asset("app.js")

        self.assertIsNotNone(js)
        self.assertIn(b"let nodes", js or b"")

    def test_default_static_app_helpers_js_exists(self) -> None:
        js = get_static_asset("app_helpers.js")

        self.assertIsNotNone(js)
        self.assertIn(b"translateCountry", js or b"")

    def test_default_static_app_quality_js_exists(self) -> None:
        js = get_static_asset("app_quality.js")

        self.assertIsNotNone(js)
        self.assertIn(b"openQualityModal", js or b"")

    def test_default_static_app_quality_render_js_exists(self) -> None:
        js = get_static_asset("app_quality_render.js")

        self.assertIsNotNone(js)
        self.assertIn(b"qualityBadgeHtml", js or b"")

    def test_default_static_app_regions_js_exists(self) -> None:
        js = get_static_asset("app_regions.js")

        self.assertIsNotNone(js)
        self.assertIn(b"openRegionsModal", js or b"")

    def test_default_static_app_regions_render_js_exists(self) -> None:
        js = get_static_asset("app_regions_render.js")

        self.assertIsNotNone(js)
        self.assertIn(b"renderRegionsList", js or b"")

    def test_default_static_app_logs_js_exists(self) -> None:
        js = get_static_asset("app_logs.js")

        self.assertIsNotNone(js)
        self.assertIn(b"openLogsModal", js or b"")

    def test_default_static_app_gateway_js_exists(self) -> None:
        js = get_static_asset("app_gateway.js")

        self.assertIsNotNone(js)
        self.assertIn(b"openGatewayModal", js or b"")

    def test_default_static_app_settings_js_exists(self) -> None:
        js = get_static_asset("app_settings.js")

        self.assertIsNotNone(js)
        self.assertIn(b"logoutAdmin", js or b"")

    def test_default_static_app_credentials_js_exists(self) -> None:
        js = get_static_asset("app_credentials.js")

        self.assertIsNotNone(js)
        self.assertIn(b"openCredentialsModal", js or b"")

    def test_default_static_app_network_settings_js_exists(self) -> None:
        js = get_static_asset("app_network_settings.js")

        self.assertIsNotNone(js)
        self.assertIn(b"openNetworkModal", js or b"")

    def test_default_static_app_routing_settings_js_exists(self) -> None:
        js = get_static_asset("app_routing_settings.js")

        self.assertIsNotNone(js)
        self.assertIn(b"selectOptionCard", js or b"")

    def test_default_static_app_favorites_js_exists(self) -> None:
        js = get_static_asset("app_favorites.js")

        self.assertIsNotNone(js)
        self.assertIn(b"toggleFavoritesView", js or b"")

    def test_default_static_app_render_js_exists(self) -> None:
        js = get_static_asset("app_render.js")

        self.assertIsNotNone(js)
        self.assertIn(b"function render", js or b"")

    def test_default_static_app_render_status_js_exists(self) -> None:
        js = get_static_asset("app_render_status.js")

        self.assertIsNotNone(js)
        self.assertIn(b"renderActiveNodeCard", js or b"")

    def test_default_static_app_node_table_js_exists(self) -> None:
        js = get_static_asset("app_node_table.js")

        self.assertIsNotNone(js)
        self.assertIn(b"renderNodeRows", js or b"")

    def test_default_static_app_actions_js_exists(self) -> None:
        js = get_static_asset("app_actions.js")

        self.assertIsNotNone(js)
        self.assertIn(b"connectNode", js or b"")

    def test_default_static_app_bootstrap_js_exists(self) -> None:
        js = get_static_asset("app_bootstrap.js")

        self.assertIsNotNone(js)
        self.assertIn(b"setInterval", js or b"")

    def test_default_static_app_events_js_exists(self) -> None:
        js = get_static_asset("app_events.js")

        self.assertIsNotNone(js)
        self.assertIn(b"addEventListener", js or b"")

    def test_default_console_static_assets_exist(self) -> None:
        css = get_static_asset("console.css")
        js = get_static_asset("console.js")

        self.assertIsNotNone(css)
        self.assertIsNotNone(js)
        self.assertIn(b":root", css or b"")
        self.assertIn(b"let instanceList", js or b"")

    def test_console_task_tab_uses_readable_chinese_label(self) -> None:
        js = (get_static_asset("console.js") or b"").decode("utf-8")

        self.assertIn('actionButton("任务与质量", "global-tasks"', js)
        self.assertNotIn(r"\\u4efb\\u52a1\\u4e0e\\u8d28\\u91cf", js)
        self.assertIn("globalSettings.scamalytics_enabled", js)
        self.assertNotIn("globalSettings.scalamalytics_enabled", js)

    def test_get_static_asset_returns_fallback_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(get_static_asset("missing.js", fallback=b"fallback", static_dir=Path(tmp)), b"fallback")

    def test_get_static_asset_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                get_static_asset("../secret.txt", static_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()
