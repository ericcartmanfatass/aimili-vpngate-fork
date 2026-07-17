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
    parser = argparse.ArgumentParser(prog="ml", description="AimiliVPN 管理命令行工具")
    parser.add_argument("--data-dir", help="为本次命令覆盖 VPNGATE_DATA_DIR")
    parser.add_argument("--json", action="store_true", help="支持时以 JSON 输出")
    subparsers = parser.add_subparsers(dest="command")

    for action in ("start", "stop", "restart"):
        service_parser = subparsers.add_parser(action, help=f"{action.capitalize()} AimiliVPN systemd 服务")
        service_parser.set_defaults(func=cmd_service_action)

    status_parser = subparsers.add_parser("status", help="查看本地服务状态")
    _add_json_flag(status_parser)
    status_parser.set_defaults(func=cmd_status)

    logs_parser = subparsers.add_parser("logs", help="使用 journalctl 查看服务日志")
    logs_parser.add_argument("-n", "--lines", type=int, default=100, help="显示的日志行数")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="持续跟踪日志")
    logs_parser.set_defaults(func=cmd_logs)

    web_parser = subparsers.add_parser("web", help="查看 Web UI 地址")
    _add_json_flag(web_parser)
    web_parser.set_defaults(func=cmd_web)

    port_parser = subparsers.add_parser("port", help="查看 UI/代理端口")
    _add_json_flag(port_parser)
    port_parser.set_defaults(func=cmd_port)

    password_parser = subparsers.add_parser("password", help="查看账户和密码状态")
    _add_json_flag(password_parser)
    password_parser.set_defaults(func=cmd_password)
    password_sub = password_parser.add_subparsers(dest="password_command")
    password_reset = password_sub.add_parser("reset", help="重置 Console 密码并仅显示一次")
    password_reset.set_defaults(func=cmd_password_reset)

    uninstall_parser = subparsers.add_parser("uninstall", help="卸载 AimiliVPN 服务，默认保留数据")
    uninstall_parser.add_argument("--yes", action="store_true", help="确认移除服务单元")
    uninstall_parser.add_argument("--delete-data", action="store_true", help="同时删除 AimiliVPN 数据目录")
    uninstall_parser.add_argument("--confirm-delete-data", action="store_true", help="与 --delete-data 一起使用")
    uninstall_parser.add_argument("--delete-source", action="store_true", help="同时删除安装源目录")
    uninstall_parser.add_argument("--confirm-delete-source", action="store_true", help="与 --delete-source 一起使用")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    nodes_parser = subparsers.add_parser("nodes", help="查看 VPN 节点")
    _add_json_flag(nodes_parser)
    _add_nodes_list_args(nodes_parser)
    nodes_parser.set_defaults(func=cmd_nodes_list)
    nodes_sub = nodes_parser.add_subparsers(dest="nodes_command")
    nodes_list = nodes_sub.add_parser("list", help="列出已知节点")
    _add_json_flag(nodes_list)
    _add_nodes_list_args(nodes_list)
    nodes_list.set_defaults(func=cmd_nodes_list)

    regions_parser = subparsers.add_parser("regions", help="查看自定义地区")
    _add_json_flag(regions_parser)
    regions_parser.set_defaults(func=cmd_regions_list)
    regions_sub = regions_parser.add_subparsers(dest="regions_command")
    regions_list = regions_sub.add_parser("list", help="列出自定义地区")
    _add_json_flag(regions_list)
    regions_list.set_defaults(func=cmd_regions_list)

    quality_parser = subparsers.add_parser("quality", help="查看质量结果和服务提供方")
    _add_json_flag(quality_parser)
    quality_parser.set_defaults(func=cmd_quality_providers)
    quality_sub = quality_parser.add_subparsers(dest="quality_command")
    quality_providers = quality_sub.add_parser("providers", help="查看质量服务状态")
    _add_json_flag(quality_providers)
    quality_providers.set_defaults(func=cmd_quality_providers)
    quality_latest = quality_sub.add_parser("latest", help="查看最新质量结果")
    _add_json_flag(quality_latest)
    quality_latest.add_argument("node_id", nargs="?", help="可选的节点 ID")
    quality_latest.set_defaults(func=cmd_quality_latest)

    return parser


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")


def _add_nodes_list_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--country", help="按国家代码筛选，例如 JP")
    parser.add_argument("--region", help="按自定义地区 ID 筛选")
    parser.add_argument("--max-risk", type=int, help="仅包含风险分数不高于此值的节点")
    parser.add_argument("--sort", choices=["none", "quality", "risk", "latency"], default="none")
    parser.add_argument("--limit", type=int, help="限制显示行数")


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
        stderr.write(f"错误: {exc}\n")
        return 1
    except KeyboardInterrupt:
        stderr.write("操作已中断\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
