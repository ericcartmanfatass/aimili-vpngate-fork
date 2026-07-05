from __future__ import annotations

from typing import Any

from aimilivpn.web.route_contexts import StatusRouteContext

def handle_status_get(handler: Any, effective_path: str, context: StatusRouteContext) -> bool:
    if effective_path != "/api/gateway_status":
        return False

    ui_cfg = context.load_ui_config()
    web_ui_status = {
        "name": "Web 管理服务",
        "status": "running",
        "details": f"监听地址: {ui_cfg.get('host', context.ui_host)}:{ui_cfg.get('port', context.ui_port)}",
        "error": "",
    }

    proxy_ok, proxy_err = context.proxy_gateway_status()
    proxy_gateway_status = {
        "name": "本地代理网关",
        "status": "running" if proxy_ok else "stopped",
        "details": f"监听地址: {context.proxy_host}:{context.proxy_port}",
        "error": proxy_err,
    }

    ovpn_ok = context.active_openvpn_running()
    active_node_id = context.active_node_id()
    ovpn_err = ""
    ovpn_details = "未连接"
    if ovpn_ok:
        ovpn_details = f"已连接节点: {active_node_id}"
        if context.is_linux() and not context.tun_exists():
            ovpn_err = f"[警告] 虚拟网卡 ({context.tun_dev}) 未启用，可能存在策略路由配置问题。"
    elif active_node_id:
        ovpn_err = "连接已中断或 OpenVPN 核心进程异常退出。"
        ovpn_details = f"尝试连接节点 {active_node_id} 失败"
    openvpn_status = {
        "name": "OpenVPN 核心连接",
        "status": "running" if ovpn_ok else "stopped",
        "details": ovpn_details,
        "error": ovpn_err,
    }

    now = context.now()
    server_uptime = now - context.server_start_time
    collector_heartbeat = context.last_collector_heartbeat()
    checker_heartbeat = context.last_checker_heartbeat()
    pinger_heartbeat = context.last_pinger_heartbeat()

    collector_ok = (collector_heartbeat > 0.0 and now - collector_heartbeat < (context.check_interval_seconds * 1.5)) or (server_uptime < 15.0)
    collector_status = {
        "name": "节点同步守护线程",
        "status": "running" if collector_ok else "stopped",
        "details": f"上次心跳: {context.format_local_time(collector_heartbeat) if collector_heartbeat > 0 else '等待启动'}",
        "error": "" if collector_ok else "线程可能已异常终止，导致无法在后台拉取和测速新节点。",
    }

    checker_ok = (checker_heartbeat > 0.0 and now - checker_heartbeat < 90.0) or (server_uptime < 35.0)
    checker_status = {
        "name": "出口检测守护线程",
        "status": "running" if checker_ok else "stopped",
        "details": f"上次心跳: {context.format_local_time(checker_heartbeat) if checker_heartbeat > 0 else '等待启动'}",
        "error": "" if checker_ok else "线程可能已挂起或终止，导致无法实时获取代理出口状态。",
    }

    pinger_ok = (pinger_heartbeat > 0.0 and now - pinger_heartbeat < 30.0) or (server_uptime < 15.0)
    pinger_status = {
        "name": "延迟测速守护线程",
        "status": "running" if pinger_ok else "stopped",
        "details": f"上次心跳: {context.format_local_time(pinger_heartbeat) if pinger_heartbeat > 0 else '等待启动'}",
        "error": "" if pinger_ok else "线程可能已中止，无法实时刷新活动节点的 Ping 延迟。",
    }

    handler.send_json({
        "ok": True,
        "services": [
            web_ui_status,
            proxy_gateway_status,
            openvpn_status,
            collector_status,
            checker_status,
            pinger_status,
        ],
    })
    return True
