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

    def test_default_console_static_assets_exist(self) -> None:
        css = get_static_asset("console.css")
        js = get_static_asset("console.js")

        self.assertIsNotNone(css)
        self.assertIsNotNone(js)
        self.assertIn(b":root", css or b"")
        self.assertIn(b"let instanceList", js or b"")

    def test_get_static_asset_returns_fallback_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(get_static_asset("missing.js", fallback=b"fallback", static_dir=Path(tmp)), b"fallback")

    def test_get_static_asset_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                get_static_asset("../secret.txt", static_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()
