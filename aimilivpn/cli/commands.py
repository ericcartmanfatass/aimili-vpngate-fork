from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

from aimilivpn.core.auth import generate_password, hash_password, utc_now_iso
from aimilivpn.core.config import AppConfig, load_config
from aimilivpn.core.models import QualityResult
from aimilivpn.core.regions import match_node
from aimilivpn.core.storage import JsonStore, NodeRepository, QualityRepository, RegionRepository
from aimilivpn.system.repository_facade import RepositoryFacade


class CliError(RuntimeError):
    pass


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class CliContext:
    def __init__(self, root_dir: Path | None = None, runner: Runner | None = None) -> None:
        self.root_dir = root_dir or Path.cwd()
        self.config = load_config(self.root_dir)
        self.repositories = RepositoryFacade(
            node_repository=NodeRepository(self.config.nodes_file),
            region_repository=RegionRepository(self.config.data_dir / "regions.json"),
            quality_repository=QualityRepository(self.config.data_dir / "quality_results.json"),
            country_translations={},
        )
        self.store = JsonStore()
        self.system_config_dir = Path(os.environ.get("AIMILIVPN_CONFIG_DIR", "/etc/aimilivpn"))
        self.install_dir = Path(os.environ.get("AIMILIVPN_INSTALL_DIR", "/opt/aimilivpn"))
        self.sysctl_file = Path(os.environ.get("AIMILIVPN_SYSCTL_FILE", "/etc/sysctl.d/99-aimilivpn.conf"))
        self.sysctl_backup = Path(
            os.environ.get(
                "AIMILIVPN_SYSCTL_BACKUP",
                str(self.system_config_dir / "backups" / "99-aimilivpn.conf.preinstall"),
            )
        )
        self.runner = runner or _run_command


def cmd_status(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    instances = instance_status_rows(ctx)
    primary = instances[0] if instances else legacy_status_row(ctx)
    services = service_status_rows(ctx)
    payload = {
        "data_dir": primary["data_dir"],
        "ui": primary["ui"],
        "local_proxy": primary["local_proxy"],
        "active_node": primary["active_node"],
        "connecting": primary["connecting"],
        "proxy_ok": primary["proxy_ok"],
        "scamalytics_configured": ctx.config.scamalytics_configured,
        "instances": instances,
        "services": services,
    }
    if args.json:
        _write_payload(payload, True, stdout)
    else:
        stdout.write(f"数据目录: {payload['data_dir']}\n")
        stdout.write(f"Web 地址: {payload['ui']}\n")
        stdout.write(f"本地代理: {payload['local_proxy']}\n")
        stdout.write(f"当前节点: {payload['active_node']}\n")
        stdout.write(f"Scamalytics 已配置: {payload['scamalytics_configured']}\n")
        if instances:
            stdout.write("\n实例:\n")
            _write_table(
                instances,
                ["id", "country", "data_dir", "ui", "local_proxy", "active_node", "connecting", "proxy_ok"],
                stdout,
                headers={"id": "ID", "country": "国家", "data_dir": "数据目录", "ui": "Web 地址", "local_proxy": "本地代理", "active_node": "当前节点", "connecting": "连接中", "proxy_ok": "代理正常"},
            )
        stdout.write("\n服务:\n")
        _write_table(services, ["service", "state"], stdout, headers={"service": "服务", "state": "状态"})
    return 0


def cmd_service_action(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    action = args.command
    services = discover_services(ctx)
    if not services:
        raise CliError("未找到 AimiliVPN systemd 服务")
    failed: list[str] = []
    for service in services:
        result = ctx.runner(["systemctl", action, service])
        if result.returncode != 0:
            failed.append(service)
    if failed:
        raise CliError(f"{action} 操作失败: {', '.join(failed)}")
    stdout.write(f"已请求对 {len(services)} 个服务执行 {action}: {', '.join(services)}\n")
    return 0


def cmd_logs(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    services = discover_services(ctx)
    if not services:
        services = ["aimilivpn.service"]
    command = ["journalctl"]
    for service in services:
        command.extend(["-u", service])
    command.extend(["-n", str(args.lines)])
    if args.follow:
        command.append("-f")
    result = ctx.runner(command)
    if result.stdout:
        stdout.write(result.stdout)
    if result.returncode != 0:
        raise CliError("journalctl 执行失败")
    return 0


def cmd_web(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    payload = web_entries(ctx)
    if args.json:
        _write_payload(payload, True, stdout)
    else:
        _write_table(payload, ["name", "url", "username", "password_set"], stdout, headers={"name": "名称", "url": "地址", "username": "用户名", "password_set": "已设置密码"})
    return 0


def cmd_port(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    rows = port_rows(ctx)
    if args.json:
        _write_payload(rows, True, stdout)
    else:
        _write_table(rows, ["name", "ui", "proxy", "tun_dev", "policy_table"], stdout, headers={"name": "名称", "ui": "Web 端口", "proxy": "代理端口", "tun_dev": "TUN 设备", "policy_table": "策略表"})
    return 0


def cmd_password(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    rows = password_rows(ctx)
    if args.json:
        _write_payload(rows, True, stdout)
    else:
        _write_table(rows, ["name", "username", "password_set", "secret_path", "note"], stdout, headers={"name": "名称", "username": "用户名", "password_set": "已设置密码", "secret_path": "安全路径", "note": "说明"})
    return 0


def cmd_password_reset(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    auth_path = ctx.system_config_dir / "console_auth.json"
    auth = read_json_file(auth_path, None)
    if not isinstance(auth, dict) or not auth_path.exists():
        raise CliError("未找到 Console 身份验证配置")

    password = generate_password(24)
    updated = dict(auth)
    updated.pop("password", None)
    updated["password_hash"] = hash_password(password)
    updated["updated_at"] = utc_now_iso()
    try:
        write_private_json(auth_path, updated)
    except OSError as exc:
        raise CliError("无法更新 Console 密码，请以 root 身份运行此命令") from exc

    result = ctx.runner(["systemctl", "restart", "aimilivpn-console.service"])
    stdout.write("Console 密码已重置，请立即保存这次显示的密码；之后不会再次显示。\n")
    stdout.write(f"密码: {password}\n")
    if result.returncode != 0:
        raise CliError("密码已更新，但 Console 重启失败；请手动重启 aimilivpn-console.service")
    return 0


def cmd_uninstall(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    if not args.yes:
        raise CliError("卸载需要 --yes；默认保留数据和源代码")
    if args.delete_data and not args.confirm_delete_data:
        raise CliError("--delete-data 需要同时指定 --confirm-delete-data")
    if args.delete_source and not args.confirm_delete_source:
        raise CliError("--delete-source 需要同时指定 --confirm-delete-source")

    instances = load_instances(ctx)
    runtime_sysctls = runtime_sysctls_for_uninstall(ctx)
    services = _unique(discover_services(ctx) + ["aimilivpn.service"])
    for service in services:
        ctx.runner(["systemctl", "stop", service])
        ctx.runner(["systemctl", "disable", service])

    for item in instances:
        table = str(item.get("policy_table") or "").strip()
        if table.isdigit():
            ctx.runner(["ip", "rule", "del", "table", table])
            ctx.runner(["ip", "route", "flush", "table", table])

    removed = []
    for path in systemd_unit_paths(ctx):
        if safe_remove_path(path):
            removed.append(str(path))
    sysctl_changed = False
    if ctx.sysctl_backup.exists():
        ctx.sysctl_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ctx.sysctl_backup, ctx.sysctl_file)
        removed.append(f"restored {ctx.sysctl_file}")
        sysctl_changed = True
    elif safe_remove_path(ctx.sysctl_file):
        removed.append(str(ctx.sysctl_file))
        sysctl_changed = True
    if sysctl_changed:
        ctx.runner(["sysctl", "--system"])
    for key, value in runtime_sysctls.items():
        ctx.runner(["sysctl", "-w", f"{key}={value}"])
    if safe_remove_path(ctx.system_config_dir, recursive=True):
        removed.append(str(ctx.system_config_dir))
    ml_path = Path(os.environ.get("AIMILIVPN_ML_PATH", "/usr/bin/ml"))
    if safe_remove_path(ml_path):
        removed.append(str(ml_path))

    if args.delete_data:
        for data_path in data_paths_for_uninstall(ctx, instances):
            if data_path.resolve() == ctx.install_dir.resolve():
                raise CliError(f"refusing to remove install directory as data: {data_path}")
            if safe_remove_path(data_path, recursive=True, allowed_roots=[ctx.install_dir]):
                removed.append(str(data_path))
    if args.delete_source:
        if safe_remove_path(ctx.install_dir, recursive=True, allowed_roots=[ctx.install_dir.parent]):
            removed.append(str(ctx.install_dir))

    ctx.runner(["systemctl", "daemon-reload"])
    ctx.runner(["systemctl", "reset-failed"])
    stdout.write("AimiliVPN 卸载操作已完成。\n")
    stdout.write("默认保留数据；如需删除，请配合确认参数使用 --delete-data。\n")
    if removed:
        stdout.write("已处理路径:\n")
        for path in removed:
            stdout.write(f"- {path}\n")
    return 0


def cmd_nodes_list(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    nodes = ctx.repositories.read_nodes()
    quality_by_node = ctx.repositories.list_latest()

    if args.country:
        country = str(args.country).strip().upper()
        nodes = [
            node for node in nodes
            if str(_node_value(node, "country_code", "country_short") or "").upper() == country
        ]

    if args.region:
        region = ctx.repositories.get(str(args.region))
        if region is None:
            raise CliError(f"未找到地区: {args.region}")
        nodes = [
            node for node in nodes
            if match_node(region, node, quality_by_node.get(str(node.get("id") or "")))
        ]

    if args.max_risk is not None:
        nodes = [
            node for node in nodes
            if _quality_value(quality_by_node.get(str(node.get("id") or "")), "risk_score") is not None
            and int(_quality_value(quality_by_node.get(str(node.get("id") or "")), "risk_score")) <= args.max_risk
        ]

    nodes = _sort_nodes(nodes, quality_by_node, args.sort)
    if args.limit is not None:
        nodes = nodes[: args.limit]

    rows = [_node_row(node, quality_by_node.get(str(node.get("id") or ""))) for node in nodes]
    if args.json:
        _write_payload(rows, True, stdout)
    else:
        _write_table(rows, ["id", "country", "ip", "latency_ms", "status", "quality_score", "risk_score", "label"], stdout, headers={"id": "ID", "country": "国家", "ip": "IP", "latency_ms": "延迟(ms)", "status": "状态", "quality_score": "质量分数", "risk_score": "风险分数", "label": "标签"})
    return 0


def cmd_regions_list(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    regions = [_region_payload(region) for region in ctx.repositories.read_regions()]
    if args.json:
        _write_payload(regions, True, stdout)
    else:
        _write_table(regions, ["id", "name", "countries", "enabled", "min_quality", "max_risk"], stdout, headers={"id": "ID", "name": "名称", "countries": "国家", "enabled": "启用", "min_quality": "最低质量", "max_risk": "最高风险"})
    return 0


def cmd_quality_providers(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    providers = [
        {"name": "local_probe", "enabled": True, "configured": True},
        {
            "name": "scamalytics",
            "enabled": ctx.config.scamalytics_configured,
            "configured": ctx.config.scamalytics_configured,
            "timeout_seconds": ctx.config.scamalytics_timeout_seconds,
            "cache_ttl_seconds": ctx.config.scamalytics_cache_ttl_seconds,
            "rate_limit_per_minute": ctx.config.scamalytics_rate_limit_per_minute,
        },
    ]
    _write_payload({"providers": providers}, args.json, stdout)
    return 0


def cmd_quality_latest(args: Any, ctx: CliContext, stdout: TextIO) -> int:
    if args.node_id:
        result = ctx.repositories.latest_for_node(args.node_id)
        if result is None:
            raise CliError(f"未找到质量结果: {args.node_id}")
        payload = _quality_payload(result)
        _write_payload(payload, args.json, stdout)
        return 0

    rows = [_quality_payload(result) for result in ctx.repositories.list_latest().values()]
    if args.json:
        _write_payload(rows, True, stdout)
    else:
        _write_table(rows, ["node_id", "exit_ip", "score", "label", "risk_score", "risk_provider", "checked_at"], stdout, headers={"node_id": "节点 ID", "exit_ip": "出口 IP", "score": "质量分数", "label": "标签", "risk_score": "风险分数", "risk_provider": "风险来源", "checked_at": "检测时间"})
    return 0


def discover_services(ctx: CliContext) -> list[str]:
    instances = load_instances(ctx)
    services = [
        str(item.get("service") or f"aimilivpn@{item.get('id')}.service")
        for item in instances
        if item.get("id") or item.get("service")
    ]
    if instances:
        services.append("aimilivpn-console.service")
    if not services:
        services.append("aimilivpn.service")
    return _unique(services)


def load_instances(ctx: CliContext) -> list[dict[str, Any]]:
    raw = ctx.store.read(ctx.system_config_dir / "instances.json", {})
    if isinstance(raw, dict) and isinstance(raw.get("instances"), list):
        return [dict(item) for item in raw["instances"] if isinstance(item, dict)]
    return []


def instance_status_rows(ctx: CliContext) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in load_instances(ctx):
        data_dir_text = str(item.get("data_dir") or "").strip()
        data_dir = Path(data_dir_text) if data_dir_text else None
        state = ctx.store.read(data_dir / "state.json", {}) if data_dir is not None else {}
        if not isinstance(state, dict):
            state = {}
        ui_host = str(item.get("ui_host") or "127.0.0.1")
        proxy_host = str(item.get("proxy_host") or "127.0.0.1")
        rows.append({
            "id": str(item.get("id") or ""),
            "country": str(item.get("country") or ""),
            "data_dir": data_dir_text,
            "ui": f"{ui_host}:{item.get('ui_port') or ''}",
            "local_proxy": f"{proxy_host}:{item.get('proxy_port') or ''}",
            "active_node": state.get("active_openvpn_node_id") or "",
            "connecting": bool(state.get("is_connecting")),
            "proxy_ok": state.get("proxy_ok"),
        })
    return rows


def legacy_status_row(ctx: CliContext) -> dict[str, Any]:
    state = ctx.store.read(ctx.config.state_file, {})
    if not isinstance(state, dict):
        state = {}
    return {
        "id": "web",
        "country": "",
        "data_dir": str(ctx.config.data_dir),
        "ui": f"{ctx.config.ui_host}:{ctx.config.ui_port}",
        "local_proxy": f"{ctx.config.local_proxy_host}:{ctx.config.local_proxy_port}",
        "active_node": state.get("active_openvpn_node_id") or "",
        "connecting": bool(state.get("is_connecting")),
        "proxy_ok": state.get("proxy_ok"),
    }


def runtime_sysctls_for_uninstall(ctx: CliContext) -> dict[str, int]:
    payload = read_json_file(ctx.system_config_dir / "network-changes.json", {})
    runtime_before = payload.get("runtime_before") if isinstance(payload, dict) else None
    if not isinstance(runtime_before, dict):
        return {}
    allowed = {
        "net.ipv4.conf.all.rp_filter",
        "net.ipv4.conf.default.rp_filter",
    }
    restored: dict[str, int] = {}
    for key, value in runtime_before.items():
        if key not in allowed or isinstance(value, bool):
            continue
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized in {0, 1, 2}:
            restored[key] = normalized
    return restored


def service_status_rows(ctx: CliContext) -> list[dict[str, str]]:
    rows = []
    for service in discover_services(ctx):
        result = ctx.runner(["systemctl", "is-active", service])
        state = (result.stdout or "").strip() or ("active" if result.returncode == 0 else "inactive")
        rows.append({"service": service, "state": state})
    return rows


def web_entries(ctx: CliContext) -> list[dict[str, Any]]:
    instances = load_instances(ctx)
    console_auth = read_json_file(ctx.system_config_dir / "console_auth.json", {})
    entries: list[dict[str, Any]] = []
    if instances or console_auth:
        host = _display_host(str(console_auth.get("host") or "0.0.0.0"))
        port = console_auth.get("port") or 8788
        secret_path = str(console_auth.get("secret_path") or "").strip("/")
        entries.append({
            "name": "console",
            "url": _url(host, port, secret_path),
            "username": console_auth.get("username") or "admin",
            "password_set": bool(console_auth.get("password_hash") or console_auth.get("password")),
        })
    for item in instances:
        auth = read_json_file(Path(str(item.get("data_dir") or "")) / "ui_auth.json", {})
        host = _display_host(str(item.get("ui_host") or auth.get("host") or "127.0.0.1"))
        port = item.get("ui_port") or auth.get("port") or ""
        secret_path = str(auth.get("secret_path") or "").strip("/")
        entries.append({
            "name": str(item.get("id") or item.get("country") or "instance"),
            "url": _url(host, port, secret_path) if port else "",
            "username": auth.get("username") or "admin",
            "password_set": bool(auth.get("password_hash") or auth.get("password")),
        })
    if not entries:
        auth = read_json_file(ctx.config.data_dir / "ui_auth.json", {})
        secret_path = str(auth.get("secret_path") or "").strip("/")
        entries.append({
            "name": "web",
            "url": _url(_display_host(ctx.config.ui_host), auth.get("port") or ctx.config.ui_port, secret_path),
            "username": auth.get("username") or "admin",
            "password_set": bool(auth.get("password_hash") or auth.get("password")),
        })
    return entries


def port_rows(ctx: CliContext) -> list[dict[str, Any]]:
    instances = load_instances(ctx)
    if instances:
        return [
            {
                "name": item.get("id") or "",
                "ui": item.get("ui_port") or "",
                "proxy": item.get("proxy_port") or "",
                "tun_dev": item.get("tun_dev") or "",
                "policy_table": item.get("policy_table") or "",
            }
            for item in instances
        ]
    auth = read_json_file(ctx.config.data_dir / "ui_auth.json", {})
    return [{
        "name": "web",
        "ui": auth.get("port") or ctx.config.ui_port,
        "proxy": auth.get("proxy_port") or ctx.config.local_proxy_port,
        "tun_dev": ctx.config.tun_dev,
        "policy_table": ctx.config.policy_table,
    }]


def password_rows(ctx: CliContext) -> list[dict[str, Any]]:
    rows = []
    for entry in web_entries(ctx):
        rows.append({
            "name": entry["name"],
            "username": entry["username"],
            "password_set": entry["password_set"],
            "secret_path": str(entry["url"]).rstrip("/").split("/")[-1] if entry.get("url") else "",
            "note": "请在 Web UI 中修改",
        })
    return rows


def systemd_unit_paths(ctx: CliContext) -> list[Path]:
    unit_dirs = [
        Path(item)
        for item in os.environ.get(
            "AIMILIVPN_SYSTEMD_UNIT_DIRS",
            "/etc/systemd/system:/lib/systemd/system:/usr/lib/systemd/system",
        ).split(":")
        if item
    ]
    names = ["aimilivpn@.service", "aimilivpn-console.service", "aimilivpn.service"]
    return [unit_dir / name for unit_dir in unit_dirs for name in names]


def data_paths_for_uninstall(ctx: CliContext, instances: list[dict[str, Any]]) -> list[Path]:
    paths = []
    for item in instances:
        data_dir = str(item.get("data_dir") or "").strip()
        if data_dir:
            paths.append(Path(data_dir))
    paths.extend([ctx.install_dir / "data", ctx.install_dir / "vpngate_data"])
    return _unique_paths(paths)


def safe_remove_path(path: Path, recursive: bool = False, allowed_roots: list[Path] | None = None) -> bool:
    try:
        target = path.resolve()
    except OSError:
        return False
    if target == Path(target.anchor):
        raise CliError(f"refusing to remove filesystem root: {target}")
    allowed_roots = [root.resolve() for root in allowed_roots or []]
    if allowed_roots and not any(target == root or root in target.parents for root in allowed_roots):
        raise CliError(f"refusing to remove path outside allowed roots: {target}")
    if not target.exists() and not target.is_symlink():
        return False
    if target.is_dir() and not target.is_symlink():
        if not recursive:
            raise CliError(f"refusing to remove directory without recursive flag: {target}")
        shutil.rmtree(target)
    else:
        target.unlink()
    return True


def _node_row(node: dict[str, Any], quality: QualityResult | None) -> dict[str, Any]:
    return {
        "id": node.get("id") or "",
        "country": _node_value(node, "country_short", "country") or "",
        "ip": _node_value(node, "ip", "remote_host") or "",
        "latency_ms": _node_value(node, "latency_ms", "ping") or "",
        "status": node.get("probe_status") or "",
        "quality_score": _quality_value(quality, "score") or node.get("quality_score") or "",
        "risk_score": _quality_value(quality, "risk_score") or "",
        "label": _quality_value(quality, "label") or node.get("quality_label") or "",
    }


def _region_payload(region: Any) -> dict[str, Any]:
    return {
        "id": region.id,
        "name": region.name,
        "countries": ",".join(region.country_codes),
        "enabled": region.enabled,
        "min_quality": region.min_quality_score if region.min_quality_score is not None else "",
        "max_risk": region.max_risk_score if region.max_risk_score is not None else "",
    }


def _quality_payload(result: QualityResult) -> dict[str, Any]:
    return {
        "node_id": result.node_id,
        "exit_ip": result.exit_ip,
        "score": result.score,
        "label": result.label,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level,
        "risk_provider": result.risk_provider,
        "checked_at": result.checked_at,
    }


def _sort_nodes(nodes: list[dict[str, Any]], quality_by_node: dict[str, QualityResult], sort_key: str) -> list[dict[str, Any]]:
    if sort_key == "quality":
        return sorted(nodes, key=lambda node: int(_quality_value(quality_by_node.get(str(node.get("id") or "")), "score") or 0), reverse=True)
    if sort_key == "risk":
        return sorted(nodes, key=lambda node: int(_quality_value(quality_by_node.get(str(node.get("id") or "")), "risk_score") or 101))
    if sort_key == "latency":
        return sorted(nodes, key=lambda node: int(_node_value(node, "latency_ms", "ping") or 999999))
    return nodes


def _node_value(node: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if node.get(key) not in (None, ""):
            return node.get(key)
    return None


def _quality_value(quality: QualityResult | None, key: str) -> Any:
    if quality is None:
        return None
    return getattr(quality, key, None)


def _write_payload(payload: Any, as_json: bool, stdout: TextIO) -> None:
    if as_json:
        stdout.write(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n")
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            stdout.write(f"{key}: {value}\n")
    else:
        stdout.write(str(payload) + "\n")


def _write_table(
    rows: list[dict[str, Any]],
    columns: list[str],
    stdout: TextIO,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    labels = headers or {}
    stdout.write("\t".join(labels.get(column, column) for column in columns) + "\n")
    for row in rows:
        stdout.write("\t".join(str(row.get(column, "")) for column in columns) + "\n")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _unique_paths(items: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for item in items:
        key = str(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _display_host(host: str) -> str:
    if host in ("", "::", "0.0.0.0"):
        return "127.0.0.1"
    return host


def _url(host: str, port: Any, secret_path: str = "") -> str:
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    path = f"/{secret_path.strip('/')}/" if secret_path else "/"
    return f"http://{host}:{port}{path}"
