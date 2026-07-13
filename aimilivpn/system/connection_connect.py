from __future__ import annotations

from pathlib import Path
from typing import Any

from aimilivpn.core.connection_state import ConnectionPhase
from aimilivpn.core.connection import (
    connection_success_state,
    mark_connection_active,
    measure_node_latency,
    normalize_node_id,
    should_clear_failed_connection,
)
from aimilivpn.core.monitoring import proxy_state_from_health


def connect_node(ctx: Any, node_id: str) -> str:
    node_id = normalize_node_id(node_id)
    stopped_existing = False

    def begin_connect() -> None:
        ctx.set_is_connecting(
            ctx.connection_runtime().begin_connect(
                node_id=node_id,
                is_connecting=ctx.get_is_connecting(),
                busy_log_message="[连接] 正在建立其他连接中，跳过此请求",
                busy_error_message="当前已有连接或节点检测任务正在运行，请稍后再试",
                active_node_latency="正在连接",
                last_check_message="正在初始化连接配置: {node_id}",
            )
        )

    ctx.run_locked(begin_connect)

    try:
        ctx.log_line("INFO", "VPN", f"开始连接节点: {node_id}")
        nodes, node = ctx.connection_runtime().prepare_target(
            node_id,
            node_matches_allowed=ctx.node_matches_allowed,
            allowed_countries=ctx.allowed_countries(),
        )

        ctx.set_state(active_node_latency="清理连接", last_check_message="正在关闭与清理旧的 VPN 连接及网卡...")
        ctx.stop_active_openvpn()
        stopped_existing = True

        ctx.set_state(active_node_latency="写入配置", last_check_message="正在写入 OpenVPN 节点配置文件...")
        config_path = Path(node["config_file"])
        try:
            ctx.write_ovpn_config(config_path, node.get("config_text") or "")
        except Exception as exc:
            raise RuntimeError(f"Failed to write configuration: {exc}") from exc

        ctx.set_state(active_node_latency="启动核心", last_check_message="正在启动 OpenVPN Core 核心服务并建立连接...")
        ok, message, process = ctx.run_openvpn_until_ready(str(node["config_file"]))
        if not ok or process is None:
            def handle_failure() -> str:
                return ctx.connection_runtime().handle_start_failure(
                    nodes=nodes,
                    node_id=node_id,
                    config_path=config_path,
                    message=message,
                    log_message_template="连接节点 {node_id} 失败: {message}",
                    print_message_template="[连接核心失败] 无法为 VPN 节点 {node_id} 建立隧道连接！详情: {message}",
                )

            ctx.set_active_node_id(ctx.run_locked(handle_failure))
            raise RuntimeError(message)

        def register_active() -> None:
            active_process, active_node_id = ctx.connection_runtime().register_active_process(process, node_id)
            ctx.set_active_connection(active_process, active_node_id)

        ctx.run_locked(register_active)

        ctx.set_state(active_node_latency="配置路由", last_check_message="正在配置策略路由规则与流量转发...")
        ctx.setup_policy_routing(ctx.tun_dev())

        ctx.set_last_active_ping_time(ctx.now())
        ctx.set_last_active_latency(0)

        ctx.set_state(active_node_latency="测试延迟", last_check_message="正在直连测试代理出口延迟与可用性...")
        try:
            latency = measure_node_latency(
                node,
                parse_int=ctx.parse_int,
                ping_latency_ms=ctx.ping_latency_ms,
            )
            if latency > 0:
                ctx.set_last_active_latency(latency)
        except Exception:
            pass

        mark_connection_active(
            nodes,
            node_id,
            proxy_host=ctx.proxy_host(),
            proxy_port=ctx.proxy_port(),
        )
        ctx.write_nodes(nodes)

        ctx.set_state(last_check_message="正在测试本地代理出站联通性与出口 IP...")
        ctx.set_state(**proxy_state_from_health(ctx.check_proxy_health()))

        ctx.set_state(
            **connection_success_state(
                node_id,
                latency_ms=ctx.get_last_active_latency(),
                timeout_label="检测超时",
            )
        )
        ctx.transition(ConnectionPhase.CONNECTED, f"connected to {node_id}", node_id)
        ctx.log_line("INFO", "VPN", f"节点 {node_id} 连接成功，出口网卡 {ctx.tun_dev()} 已启用")
        return f"Connected {node_id}"
    except Exception as exc:
        ctx.log_line("ERROR", "VPN", f"connection attempt failed: {type(exc).__name__}: {exc}")
        ctx.transition(ConnectionPhase.FAILED, "connection failed")
        if should_clear_failed_connection(
            stopped_existing=stopped_existing,
            active_node_id=ctx.get_active_node_id(),
            requested_node_id=node_id,
            active_running=ctx.active_openvpn_running(),
        ):
            ctx.clear_active_connection_state("connection failed")
        else:
            ctx.set_state(is_connecting=False, last_check_message="connection failed")
        raise
    finally:
        def finish_connecting() -> None:
            ctx.set_is_connecting(ctx.connection_runtime().finish_connecting())

        ctx.run_locked(finish_connecting)

