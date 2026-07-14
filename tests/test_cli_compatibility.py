from __future__ import annotations

import argparse
import ast
import unittest
from pathlib import Path

from aimilivpn.cli.main import build_parser


ROOT = Path(__file__).resolve().parents[1]
CLI_DIR = ROOT / "aimilivpn" / "cli"


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    action = next(
        item for item in parser._actions
        if isinstance(item, argparse._SubParsersAction)
    )
    return action.choices


class CliCompatibilityTests(unittest.TestCase):
    def test_command_hierarchy_and_order_remain_compatible(self) -> None:
        commands = _subcommands(build_parser())

        self.assertEqual(
            list(commands),
            [
                "start",
                "stop",
                "restart",
                "status",
                "logs",
                "web",
                "port",
                "password",
                "uninstall",
                "nodes",
                "regions",
                "quality",
            ],
        )
        self.assertEqual(list(_subcommands(commands["password"])), ["reset"])
        self.assertEqual(list(_subcommands(commands["nodes"])), ["list"])
        self.assertEqual(list(_subcommands(commands["regions"])), ["list"])
        self.assertEqual(list(_subcommands(commands["quality"])), ["providers", "latest"])

    def test_cli_has_no_frontend_or_http_client_dependency(self) -> None:
        forbidden_modules = (
            "aimilivpn.web",
            "aiohttp",
            "http.client",
            "httpx",
            "requests",
            "urllib.request",
        )

        for path in sorted(CLI_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported_modules: list[str] = []
            command_tokens: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.append(node.module)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    command_tokens.append(node.value)

            for module in imported_modules:
                self.assertFalse(
                    any(module == forbidden or module.startswith(f"{forbidden}.") for forbidden in forbidden_modules),
                    f"{path.name} must not depend on frontend or HTTP client module {module}",
                )
            self.assertNotIn("curl", command_tokens, f"{path.name} must not shell out to curl")
            self.assertNotIn("wget", command_tokens, f"{path.name} must not shell out to wget")


if __name__ == "__main__":
    unittest.main()
