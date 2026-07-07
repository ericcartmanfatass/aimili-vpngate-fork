from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimilivpn.web.templates import (
    get_console_index_html,
    get_console_login_html,
    get_index_html,
    get_login_html,
    get_template,
)


class WebTemplateTests(unittest.TestCase):
    def test_get_template_returns_fallback_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = get_template("login.html", "<html>fallback</html>", template_dir=Path(tmp))

            self.assertEqual(html, "<html>fallback</html>")

    def test_get_template_prefers_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp)
            (template_dir / "login.html").write_text("<html>file</html>", encoding="utf-8")

            html = get_template("login.html", "<html>fallback</html>", template_dir=template_dir)

            self.assertEqual(html, "<html>file</html>")

    def test_get_template_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            get_template("../login.html", "fallback")

    def test_named_helpers_return_html_fallback(self) -> None:
        self.assertIn("<html", get_login_html("<html>login</html>"))
        self.assertIn("<html", get_index_html("<html>index</html>"))

    def test_named_helpers_read_default_template_files(self) -> None:
        login = get_login_html("fallback")
        index = get_index_html("fallback")

        self.assertNotEqual(login, "fallback")
        self.assertNotEqual(index, "fallback")
        self.assertIn("<html", login.lower())
        self.assertIn("<html", index.lower())
        self.assertIn("AimiliVPN", login)
        self.assertIn("AimiliVPN", index)

    def test_index_template_references_external_stylesheet(self) -> None:
        index = get_index_html("fallback")

        self.assertIn('href="./static/style.css"', index)
        self.assertNotIn("<style>", index)
        self.assertNotIn("</style>", index)

    def test_index_template_references_external_script(self) -> None:
        index = get_index_html("fallback")

        self.assertIn('src="./static/app_helpers.js"', index)
        self.assertIn('src="./static/app_quality.js"', index)
        self.assertIn('src="./static/app_regions.js"', index)
        self.assertIn('src="./static/app_gateway.js"', index)
        self.assertIn('src="./static/app_logs.js"', index)
        self.assertIn('src="./static/app_settings.js"', index)
        self.assertIn('src="./static/app_render.js"', index)
        self.assertIn('src="./static/app.js"', index)
        self.assertLess(
            index.index('src="./static/app_helpers.js"'),
            index.index('src="./static/app_quality.js"'),
        )
        self.assertLess(
            index.index('src="./static/app_quality.js"'),
            index.index('src="./static/app_regions.js"'),
        )
        self.assertLess(
            index.index('src="./static/app_regions.js"'),
            index.index('src="./static/app_gateway.js"'),
        )
        self.assertLess(
            index.index('src="./static/app_gateway.js"'),
            index.index('src="./static/app_logs.js"'),
        )
        self.assertLess(
            index.index('src="./static/app_logs.js"'),
            index.index('src="./static/app_settings.js"'),
        )
        self.assertLess(
            index.index('src="./static/app_settings.js"'),
            index.index('src="./static/app_render.js"'),
        )
        self.assertLess(
            index.index('src="./static/app_render.js"'),
            index.index('src="./static/app.js"'),
        )
        self.assertNotIn("<script>\nlet nodes", index)

    def test_console_helpers_read_default_template_files(self) -> None:
        login = get_console_login_html("fallback")
        index = get_console_index_html("fallback")

        self.assertNotEqual(login, "fallback")
        self.assertNotEqual(index, "fallback")
        self.assertIn("<html", login.lower())
        self.assertIn("<html", index.lower())
        self.assertIn("AimiliVPN Console", login)
        self.assertIn("AimiliVPN Console", index)

    def test_console_index_template_references_external_assets(self) -> None:
        index = get_console_index_html("fallback")

        self.assertIn('href="./static/console.css"', index)
        self.assertIn('src="./static/console.js"', index)
        self.assertNotIn("<style>", index)
        self.assertNotIn("<script>\nlet instanceList", index)


if __name__ == "__main__":
    unittest.main()
