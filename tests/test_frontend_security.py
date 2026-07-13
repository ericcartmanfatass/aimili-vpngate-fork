from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "aimilivpn" / "web"


class FrontendSecurityTests(unittest.TestCase):
    def test_templates_and_scripts_have_no_inline_event_handlers(self) -> None:
        inline_event = re.compile(r"(?:\bon[a-z]+|\.on[a-z]+)\s*=", re.IGNORECASE)
        paths = [*WEB_ROOT.joinpath("templates").glob("*.html"), *WEB_ROOT.joinpath("static").glob("*.js")]

        for path in paths:
            self.assertIsNone(inline_event.search(path.read_text(encoding="utf-8")), path.name)

    def test_security_sensitive_renderers_do_not_use_html_sinks(self) -> None:
        for name in ("app_render_status.js", "app_logs.js", "console.js"):
            source = WEB_ROOT.joinpath("static", name).read_text(encoding="utf-8")
            self.assertNotIn("innerHTML", source, name)
            self.assertNotIn("insertAdjacentHTML", source, name)
            self.assertIn("textContent", source, name)

    def test_frontend_does_not_persist_server_data_in_browser_storage(self) -> None:
        source = "\n".join(path.read_text(encoding="utf-8") for path in WEB_ROOT.joinpath("static").glob("*.js"))

        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)

    def test_console_uses_only_controlled_instance_lifecycle_api(self) -> None:
        source = WEB_ROOT.joinpath("static", "console.js").read_text(encoding="utf-8")

        self.assertIn('api("instance-catalog")', source)
        self.assertIn('api("instances", {', source)
        self.assertIn('retain_data: !purgeData', source)
        self.assertIn('purge_data_confirmation: purgeConfirmation', source)
        self.assertNotRegex(source, r"systemctl|/etc/|\.service\s*=")

    def test_dashboard_uses_frozen_api_pagination_and_bulk_operations(self) -> None:
        app_source = WEB_ROOT.joinpath("static", "app.js").read_text(encoding="utf-8")
        action_source = WEB_ROOT.joinpath("static", "app_actions.js").read_text(encoding="utf-8")

        self.assertIn("./api/v1/nodes?", app_source)
        self.assertIn("limit: String(pageSize)", app_source)
        self.assertIn("offset: String((currentPage - 1) * pageSize)", app_source)
        self.assertNotIn("99999", app_source)
        self.assertIn("./api/v1/quality-checks/nodes", action_source)


if __name__ == "__main__":
    unittest.main()
