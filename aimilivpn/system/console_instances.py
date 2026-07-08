from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from aimilivpn.system.console_config import CONFIG_DIR, INSTALL_DIR, INSTANCES_FILE, read_json


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return default


def _first_int(*values: Any, default: int = 0) -> int:
    text = _first_text(*values)
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _proxy_url(host: Any, port: Any) -> str:
    host_text = _first_text(host, default="127.0.0.1")
    host_part = f"[{host_text}]" if ":" in host_text and not host_text.startswith("[") else host_text
    return f"socks5://{host_part}:{_first_int(port)}"


def normalize_instance(item: dict[str, Any]) -> dict[str, Any]:
    iid = _first_text(item.get("id"), item.get("instance_id"), item.get("country")).lower()
    env_file = Path(_first_text(item.get("env_file"), default=str(CONFIG_DIR / f"{iid}.env")))
    env = parse_env_file(env_file)
    country = _first_text(item.get("country"), env.get("ALLOWED_COUNTRIES"), default=iid).upper()
    data_dir = _first_text(item.get("data_dir"), env.get("VPNGATE_DATA_DIR"), default=str(INSTALL_DIR / "data" / iid))
    ui_port = _first_int(item.get("ui_port"), env.get("UI_PORT"))
    proxy_port = _first_int(item.get("proxy_port"), env.get("LOCAL_PROXY_PORT"))
    auth = read_json(Path(data_dir) / "ui_auth.json", {})
    secret = str(auth.get("secret_path") or "EJsW2EeBo9lY")
    return {
        "id": iid,
        "country": country,
        "service": str(item.get("service") or f"aimilivpn@{iid}.service"),
        "env_file": str(env_file),
        "data_dir": data_dir,
        "ui_host": _first_text(item.get("ui_host"), env.get("UI_HOST"), default="127.0.0.1"),
        "ui_port": ui_port,
        "proxy_host": _first_text(item.get("proxy_host"), env.get("LOCAL_PROXY_HOST"), default="127.0.0.1"),
        "proxy_port": proxy_port,
        "tun_dev": _first_text(item.get("tun_dev"), env.get("TUN_DEV")),
        "policy_table": _first_text(item.get("policy_table"), env.get("POLICY_TABLE")),
        "secret_path": secret,
    }


def load_instances() -> list[dict[str, Any]]:
    data = read_json(INSTANCES_FILE, {})
    raw_instances = data.get("instances") if isinstance(data, dict) else None
    if isinstance(raw_instances, list) and raw_instances:
        return [normalize_instance(item) for item in raw_instances if isinstance(item, dict)]

    instances = []
    for env_file in sorted(CONFIG_DIR.glob("*.env")):
        iid = env_file.stem.lower()
        instances.append(normalize_instance({"id": iid, "env_file": str(env_file)}))
    return instances


def instance_by_id(instance_id: str) -> dict[str, Any] | None:
    target = instance_id.lower()
    for inst in load_instances():
        if inst["id"] == target:
            return inst
    return None


def instance_state(
    inst: dict[str, Any],
    *,
    service_active: Callable[[str], bool],
) -> dict[str, Any]:
    data_dir = Path(inst["data_dir"])
    state = read_json(data_dir / "state.json", {})
    nodes = read_json(data_dir / "nodes.json", [])
    active_id = state.get("active_openvpn_node_id", "")
    active_node = None
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("id") == active_id:
                active_node = {
                    "id": node.get("id"),
                    "ip": node.get("ip") or node.get("remote_host"),
                    "country": node.get("country"),
                    "latency_ms": node.get("latency_ms"),
                    "quality": node.get("quality"),
                }
                break
    return {
        "id": inst["id"],
        "country": inst["country"],
        "service": inst["service"],
        "service_active": service_active(inst["service"]),
        "data_dir": inst["data_dir"],
        "ui_port": inst["ui_port"],
        "proxy_port": inst["proxy_port"],
        "tun_dev": inst["tun_dev"],
        "policy_table": inst["policy_table"],
        "local_proxy": _proxy_url(inst.get("proxy_host"), inst.get("proxy_port")),
        "state": state if isinstance(state, dict) else {},
        "active_node": active_node,
    }


def stripped_nodes(
    inst: dict[str, Any],
    *,
    state_factory: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    nodes = read_json(Path(inst["data_dir"]) / "nodes.json", [])
    clean = []
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            item = dict(node)
            item.pop("config_text", None)
            clean.append(item)
    return {"nodes": clean, "state": state_factory(inst)}


def read_logs(inst: dict[str, Any]) -> dict[str, Any]:
    logs_dir = Path(inst["data_dir"]) / "logs"
    today = time.strftime("%Y-%m-%d", time.localtime())
    log_file = logs_dir / f"{today}.json"
    entries = []
    if log_file.exists():
        try:
            for line in log_file.read_text(encoding="utf-8").splitlines()[-300:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        except OSError:
            pass
    return {"logs": entries}
