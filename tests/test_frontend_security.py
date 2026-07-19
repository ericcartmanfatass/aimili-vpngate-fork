from __future__ import annotations

import ast
import html
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "aimilivpn" / "web"


class FrontendSecurityTests(unittest.TestCase):
    TECHNICAL_TERMS = {
        "aimilivpn", "api", "asn", "console", "http", "https", "ip", "json", "key",
        "openvpn", "scamalytics", "sha", "socks", "sqlite", "tls", "ui", "url", "vpngate", "web",
    }

    def test_frontend_has_no_external_runtime_assets(self) -> None:
        paths = [
            *WEB_ROOT.joinpath("templates").glob("*.html"),
            *WEB_ROOT.joinpath("static").glob("*.css"),
            *WEB_ROOT.joinpath("static").glob("*.js"),
        ]

        for path in paths:
            source = path.read_text(encoding="utf-8")
            lowered = source.lower()
            self.assertNotIn("fonts.googleapis.com", lowered, path.name)
            self.assertNotIn("fonts.gstatic.com", lowered, path.name)
            self.assertNotRegex(lowered, r"@import\s+(?:url\s*\()?\s*['\"]?(?:https?:)?//", path.name)
            self.assertNotRegex(lowered, r"url\(\s*['\"]?(?:https?:)?//", path.name)
            self.assertNotRegex(
                lowered,
                r"<(?:script|img|link)\b[^>]*(?:src|href)\s*=\s*['\"]?(?:https?:)?//",
                path.name,
            )
            self.assertNotRegex(
                lowered,
                r"\bimport\s*(?:\(|[^;\n]*?from\s*)['\"](?:https?:)?//",
                path.name,
            )

    def test_frontend_files_are_utf8_and_have_no_replacement_or_mojibake_markers(self) -> None:
        paths = [*WEB_ROOT.joinpath("templates").glob("*.html"), *WEB_ROOT.joinpath("static").glob("*.*")]
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertEqual(source.encode("utf-8").decode("utf-8"), source, path.name)
            self.assertNotIn("\ufffd", source, path.name)
            self.assertNotRegex(source, r"(?:Ã.|Â.|â€.){2,}", path.name)

    def test_console_v103_uses_filterable_nodes_and_redacted_log_export(self) -> None:
        source = WEB_ROOT.joinpath("static", "console.js").read_text(encoding="utf-8")
        for expected in (
            "availability", "riskLevel", "minRisk", "maxRisk", "cacheState", "minLatency", "updatedAfter", "downloadRedactedLogs",
            "redactLogText", "globalVpnGateRetryBackoff", "globalInstanceRetryBackoff",
            "connection_candidate_limit", "suppressed_count", "latest_backup", "last_restore",
            "instance_storage", "focusQueue", "instanceFilter", "serviceInstance",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, source)

    def test_targeted_user_visible_validation_messages_are_chinese(self) -> None:
        paths = [
            ROOT / "aimilivpn" / "core" / "global_config.py",
            ROOT / "aimilivpn" / "system" / "instance_lifecycle.py",
            ROOT / "aimilivpn" / "system" / "console_instances.py",
        ]
        forbidden = (
            "must be an http", "must not contain credentials", "must be boolean",
            "must use HH:MM", "already exists", "country is not available",
            "data path is not managed", "instance creation failed", "invalid instance id",
        )
        source = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
        for phrase in forbidden:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase.lower(), source)

    def test_console_user_interface_does_not_regress_to_english_copy(self) -> None:
        paths = [
            WEB_ROOT / "static" / "console.js",
            WEB_ROOT / "templates" / "console_index.html",
            WEB_ROOT / "templates" / "console_login.html",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        forbidden = (
            "Global VPNGate orchestration console",
            "Managed instances",
            "Create and start",
            "No managed instances",
            "Logs & Security",
            "Sign in",
            "Sign out",
        )
        for phrase in forbidden:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, source)

    def test_visible_english_only_html_uses_an_explicit_whitelist(self) -> None:
        allowed = {
            "AimiliVPN",
            "Console",
            "GITHUB",
            "Telegram",
            "339936.xyz",
            "BNB (BSC):",
            "0xB6d78c42CEB0687A31B8cfEBE4b51b6eB8953C17",
            "TRX (TRC20):",
            "TSdzCW6JvsrqcppodYjhSrku4mYmDJ9pxf",
        }
        for path in WEB_ROOT.joinpath("templates").glob("*.html"):
            source = path.read_text(encoding="utf-8")
            source = re.sub(r"<(?:script|style)\b.*?</(?:script|style)>", " ", source, flags=re.I | re.S)
            visible = html.unescape(re.sub(r"<[^>]+>", "\n", source))
            english_only = {
                line.strip()
                for line in visible.splitlines()
                if line.strip()
                and re.search(r"[A-Za-z]", line)
                and not re.search(r"[\u3400-\u9fff]", line)
            }
            self.assertEqual(english_only - allowed, set(), f"{path.name} 存在未列入白名单的英文可见文本")

    def test_javascript_visible_labels_are_chinese_or_whitelisted_technical_terms(self) -> None:
        visible_calls = (
            re.compile(r"(?:actionButton|setOperation|showError|confirm|prompt|Option)\(\s*(?P<quote>[\"'`])(?P<text>[^\"'`\n]*)(?P=quote)"),
            re.compile(r"accessible\(\s*[^,\n]+,\s*(?P<quote>[\"'`])(?P<text>[^\"'`\n]*)(?P=quote)"),
            re.compile(r"dom\(\s*[^,\n]+,\s*[^,\n]+,\s*(?P<quote>[\"'`])(?P<text>[^\"'`\n]*)(?P=quote)"),
        )
        for path in WEB_ROOT.joinpath("static").glob("*.js"):
            source = path.read_text(encoding="utf-8")
            matches = (match for pattern in visible_calls for match in pattern.finditer(source))
            for match in matches:
                value = match.group("text")
                if not re.search(r"[A-Za-z]", value) or re.search(r"[\u3400-\u9fff]", value):
                    continue
                words = {word.lower() for word in re.findall(r"[A-Za-z]{2,}", value)}
                self.assertTrue(
                    words <= self.TECHNICAL_TERMS,
                    f"{path.name} 存在未列入技术名白名单的英文界面文本: {value}",
                )

    def test_project_generated_python_log_summaries_are_chinese(self) -> None:
        roots = [ROOT / "aimilivpn" / "core", ROOT / "aimilivpn" / "system", ROOT / "aimilivpn" / "web"]
        for folder in roots:
            for path in folder.glob("*.py"):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    name = ""
                    if isinstance(node.func, ast.Name):
                        name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                    if name not in {"print", "debug", "info", "warning", "error", "critical", "exception"}:
                        continue
                    value = " ".join(
                        item.value for item in ast.walk(node)
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    )
                    words = {word.lower() for word in re.findall(r"[A-Za-z]{2,}", value)}
                    if not words or re.search(r"[\u3400-\u9fff]", value):
                        continue
                    self.assertTrue(
                        words <= self.TECHNICAL_TERMS,
                        f"{path.name} 存在无中文摘要的项目日志: {value}",
                    )

    def test_logs_do_not_receive_secret_values_or_full_urls(self) -> None:
        sensitive = re.compile(r"(?:password|api_?key|session|token|credential|secret|url)", re.I)
        for path in ROOT.joinpath("aimilivpn").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                else:
                    name = ""
                if name not in {"print", "debug", "info", "warning", "error", "critical", "exception"}:
                    continue
                identifiers = {
                    item.id for item in ast.walk(node) if isinstance(item, ast.Name)
                } | {
                    item.attr for item in ast.walk(node) if isinstance(item, ast.Attribute)
                }
                unsafe = {
                    value for value in identifiers
                    if sensitive.search(value) and not re.search(r"(?:file|path)$", value, re.I)
                }
                self.assertEqual(unsafe, set(), f"{path.name} 的日志调用直接引用敏感变量: {sorted(unsafe)}")

    def test_console_error_routes_use_the_stable_error_contract(self) -> None:
        source = ROOT.joinpath("aimilivpn", "system", "console_routes.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?:send_json|safe_error_json)\(\{[^\n]*[\"']error[\"']")
        for key in ('"error_code"', '"message"', '"details"'):
            self.assertIn(key, source)
        for code in (
            "internal_server_error", "unauthorized", "not_found", "instance_not_found",
            "request_too_large", "invalid_request_body", "request_timeout", "login_failed",
        ):
            self.assertIn(f'api_error("{code}"', source)

    def test_generated_password_is_never_interpolated_into_logs(self) -> None:
        paths = [
            ROOT / "aimilivpn" / "system" / "console_config.py",
            ROOT / "aimilivpn" / "system" / "ui_config.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotRegex(source, r"(?:print|log(?:ger)?\.(?:info|warning|error))\([^\n]*generated_password")
        self.assertIn("write_initial_credentials", source)
        self.assertIn("_write_initial_credentials", source)
        self.assertIn("0o600", source)

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
