from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, TextIO

from .commands import (
    CliContext,
    CliError,
    cmd_logs,
    cmd_nodes_list,
    cmd_password,
    cmd_password_reset,
    cmd_port,
    cmd_quality_latest,
    cmd_quality_providers,
    cmd_regions_list,
    cmd_service_action,
    cmd_status,
    cmd_uninstall,
    cmd_web,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ml", description="AimiliVPN management CLI")
    parser.add_argument("--data-dir", help="Override VPNGATE_DATA_DIR for this command")
    parser.add_argument("--json", action="store_true", help="Output JSON when supported")
    subparsers = parser.add_subparsers(dest="command")

    for action in ("start", "stop", "restart"):
        service_parser = subparsers.add_parser(action, help=f"{action.capitalize()} AimiliVPN systemd services")
        service_parser.set_defaults(func=cmd_service_action)

    status_parser = subparsers.add_parser("status", help="Show local service state")
    _add_json_flag(status_parser)
    status_parser.set_defaults(func=cmd_status)

    logs_parser = subparsers.add_parser("logs", help="Show service logs with journalctl")
    logs_parser.add_argument("-n", "--lines", type=int, default=100, help="Number of journal lines")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow logs")
    logs_parser.set_defaults(func=cmd_logs)

    web_parser = subparsers.add_parser("web", help="Show Web UI URLs")
    _add_json_flag(web_parser)
    web_parser.set_defaults(func=cmd_web)

    port_parser = subparsers.add_parser("port", help="Show UI/proxy ports")
    _add_json_flag(port_parser)
    port_parser.set_defaults(func=cmd_port)

    password_parser = subparsers.add_parser("password", help="Show account/password status")
    _add_json_flag(password_parser)
    password_parser.set_defaults(func=cmd_password)
    password_sub = password_parser.add_subparsers(dest="password_command")
    password_reset = password_sub.add_parser("reset", help="Reset the Console password and show it once")
    password_reset.set_defaults(func=cmd_password_reset)

    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall AimiliVPN services; preserves data by default")
    uninstall_parser.add_argument("--yes", action="store_true", help="Confirm service/unit removal")
    uninstall_parser.add_argument("--delete-data", action="store_true", help="Also delete AimiliVPN data directories")
    uninstall_parser.add_argument("--confirm-delete-data", action="store_true", help="Required with --delete-data")
    uninstall_parser.add_argument("--delete-source", action="store_true", help="Also delete the install source directory")
    uninstall_parser.add_argument("--confirm-delete-source", action="store_true", help="Required with --delete-source")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    nodes_parser = subparsers.add_parser("nodes", help="Inspect VPN nodes")
    _add_json_flag(nodes_parser)
    _add_nodes_list_args(nodes_parser)
    nodes_parser.set_defaults(func=cmd_nodes_list)
    nodes_sub = nodes_parser.add_subparsers(dest="nodes_command")
    nodes_list = nodes_sub.add_parser("list", help="List known nodes")
    _add_json_flag(nodes_list)
    _add_nodes_list_args(nodes_list)
    nodes_list.set_defaults(func=cmd_nodes_list)

    regions_parser = subparsers.add_parser("regions", help="Inspect custom regions")
    _add_json_flag(regions_parser)
    regions_parser.set_defaults(func=cmd_regions_list)
    regions_sub = regions_parser.add_subparsers(dest="regions_command")
    regions_list = regions_sub.add_parser("list", help="List custom regions")
    _add_json_flag(regions_list)
    regions_list.set_defaults(func=cmd_regions_list)

    quality_parser = subparsers.add_parser("quality", help="Inspect quality results and providers")
    _add_json_flag(quality_parser)
    quality_parser.set_defaults(func=cmd_quality_providers)
    quality_sub = quality_parser.add_subparsers(dest="quality_command")
    quality_providers = quality_sub.add_parser("providers", help="Show quality provider status")
    _add_json_flag(quality_providers)
    quality_providers.set_defaults(func=cmd_quality_providers)
    quality_latest = quality_sub.add_parser("latest", help="Show latest quality results")
    _add_json_flag(quality_latest)
    quality_latest.add_argument("node_id", nargs="?", help="Optional node id")
    quality_latest.set_defaults(func=cmd_quality_latest)

    return parser


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output JSON")


def _add_nodes_list_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--country", help="Filter by country code, for example JP")
    parser.add_argument("--region", help="Filter by custom region id")
    parser.add_argument("--max-risk", type=int, help="Only include nodes with risk score at or below this value")
    parser.add_argument("--sort", choices=["none", "quality", "risk", "latency"], default="none")
    parser.add_argument("--limit", type=int, help="Limit number of rows")


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    root_dir: Path | None = None,
    runner=None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help(stderr)
        return 2

    if args.data_dir:
        import os

        os.environ["VPNGATE_DATA_DIR"] = str(Path(args.data_dir).resolve())

    try:
        ctx = CliContext(root_dir=root_dir, runner=runner)
        return int(args.func(args, ctx, stdout) or 0)
    except CliError as exc:
        stderr.write(f"error: {exc}\n")
        return 1
    except KeyboardInterrupt:
        stderr.write("interrupted\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
