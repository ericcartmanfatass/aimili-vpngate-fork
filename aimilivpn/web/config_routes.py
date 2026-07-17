from __future__ import annotations

import re
from http import HTTPStatus
from typing import Any

from aimilivpn.web.api_errors import send_api_error, send_client_error
from aimilivpn.web.route_contexts import ConfigRouteContext

def handle_config_post(handler: Any, effective_path: str, context: ConfigRouteContext) -> bool:
    if effective_path == "/api/update_credentials":
        try:
            payload = handler.read_json_body()
            new_username = str(payload.get("username") or "").strip()
            new_password = str(payload.get("password") or "").strip()
            new_port = payload.get("port")
            new_suffix = str(payload.get("secret_path") or "").strip()

            ui_cfg = context.load_ui_config()
            if not new_username or (not new_password and not ui_cfg.get("password_hash")):
                handler.send_json({"ok": False, "error": "用户名不能为空；首次设置时密码不能为空"}, HTTPStatus.BAD_REQUEST)
                return True

            try:
                new_port_int = int(new_port)
                if not (1 <= new_port_int <= 65535):
                    raise ValueError()
            except (TypeError, ValueError):
                handler.send_json({"ok": False, "error": "网页登录端口范围必须是 1 到 65535"}, HTTPStatus.BAD_REQUEST)
                return True

            if not new_suffix or not re.match(r"^[A-Za-z0-9]+$", new_suffix):
                handler.send_json({"ok": False, "error": "安全后缀只能由英文字母和数字组成"}, HTTPStatus.BAD_REQUEST)
                return True

            expected_username = ui_cfg.get("username", "")
            expected_port = ui_cfg.get("port", 8787)
            expected_suffix = ui_cfg.get("secret_path", "EJsW2EeBo9lY")

            ui_cfg["username"] = new_username
            if new_password:
                ui_cfg["password"] = new_password
            ui_cfg["port"] = new_port_int
            ui_cfg["secret_path"] = new_suffix

            reauth_required = (
                new_username != expected_username
                or bool(new_password)
                or new_suffix != expected_suffix
            )
            context.save_ui_config(ui_cfg)
            if reauth_required:
                context.clear_sessions()

            restart_needed = new_port_int != expected_port or new_suffix != expected_suffix
            if restart_needed:
                handler.send_json({
                    "ok": True,
                    "restart_needed": True,
                    "reauth_required": reauth_required,
                    "message": "配置更新成功，网页登录端口或路径已变更，将在 2 秒内重启...",
                })
                context.schedule_restart("管理后台安全配置更新，进程即将退出以触发自动重启...")
            else:
                handler.send_json({
                    "ok": True,
                    "restart_needed": False,
                    "reauth_required": reauth_required,
                    "message": "账号密码配置更新成功，已即时生效。",
                })
        except Exception as exc:
            send_api_error(handler, "configuration_failed", exc=exc, operation="credential update")
        return True

    if effective_path == "/api/update_settings":
        try:
            payload = handler.read_json_body()
            new_proxy_port = payload.get("proxy_port")
            routing_mode = str(payload.get("routing_mode") or "auto").strip()
            force_country = str(payload.get("force_country") or "").strip()
            routing_ip_type = str(payload.get("routing_ip_type") or "all").strip()

            try:
                new_proxy_port_int = int(new_proxy_port)
                if not (1024 <= new_proxy_port_int <= 65535):
                    raise ValueError()
            except (TypeError, ValueError):
                handler.send_json({"ok": False, "error": "代理出站端口范围必须是 1024 到 65535"}, HTTPStatus.BAD_REQUEST)
                return True

            if routing_mode not in ("auto", "fixed_ip", "fixed_region", "favorites"):
                handler.send_json({"ok": False, "error": "无效的路由配置模式"}, HTTPStatus.BAD_REQUEST)
                return True
            if routing_ip_type not in ("all", "residential", "hosting"):
                handler.send_json({"ok": False, "error": "无效的 IP 出站类型过滤"}, HTTPStatus.BAD_REQUEST)
                return True
            try:
                context.validate_routing_region_target(routing_mode, force_country)
            except ValueError as exc:
                send_client_error(handler, "invalid_configuration", "地区不存在")
                return True

            ui_cfg = context.load_ui_config()
            expected_proxy_port = ui_cfg.get("proxy_port", 7928)
            if new_proxy_port_int == ui_cfg.get("port", 8787):
                handler.send_json({"ok": False, "error": "代理出站端口不能与网页登录端口相同"}, HTTPStatus.BAD_REQUEST)
                return True

            ui_cfg["proxy_port"] = new_proxy_port_int
            ui_cfg["routing_mode"] = routing_mode
            ui_cfg["force_country"] = force_country
            ui_cfg["routing_ip_type"] = routing_ip_type
            context.save_ui_config(ui_cfg)

            restart_needed = new_proxy_port_int != expected_proxy_port
            if restart_needed:
                handler.send_json({"ok": True, "restart_needed": True, "message": "配置更新成功，代理出站端口变更，将在 2 秒内重启..."})
                context.schedule_restart("代理出站端口变更，进程即将退出以触发自动重启...")
            else:
                handler.send_json({"ok": True, "restart_needed": False, "message": "配置更新成功，已即时生效。"})
        except Exception as exc:
            send_api_error(handler, "configuration_failed", exc=exc, operation="settings update")
        return True

    if effective_path == "/api/update_routing":
        try:
            payload = handler.read_json_body()
            routing_mode = str(payload.get("routing_mode") or "auto").strip()
            force_country = str(payload.get("force_country") or "").strip()
            routing_ip_type = str(payload.get("routing_ip_type") or "all").strip()
            fav_fail_fallback = bool(payload.get("fav_fail_fallback", True))

            if routing_mode not in ("auto", "fixed_ip", "fixed_region", "favorites"):
                handler.send_json({"ok": False, "error": "无效的路由配置模式"}, HTTPStatus.BAD_REQUEST)
                return True
            if routing_ip_type not in ("all", "residential", "hosting"):
                handler.send_json({"ok": False, "error": "无效的 IP 出站类型过滤"}, HTTPStatus.BAD_REQUEST)
                return True
            try:
                context.validate_routing_region_target(routing_mode, force_country)
            except ValueError as exc:
                send_client_error(handler, "invalid_configuration", "地区不存在")
                return True

            ui_cfg = context.load_ui_config()
            ui_cfg["routing_mode"] = routing_mode
            ui_cfg["force_country"] = force_country
            ui_cfg["routing_ip_type"] = routing_ip_type
            ui_cfg["fav_fail_fallback"] = fav_fail_fallback
            ui_cfg.pop("enable_force_country", None)
            context.save_ui_config(ui_cfg)
            handler.send_json({"ok": True, "message": "出站路由配置更新成功，已即时生效。"})
        except Exception as exc:
            send_api_error(handler, "configuration_failed", exc=exc, operation="routing update")
        return True

    if effective_path == "/api/toggle_favorite":
        try:
            payload = handler.read_json_body()
            node_id = str(payload.get("id") or "").strip()
            ui_cfg = context.load_ui_config()
            fav_ids = ui_cfg.get("favorite_node_ids", [])
            if not isinstance(fav_ids, list):
                fav_ids = []

            if node_id in fav_ids:
                fav_ids.remove(node_id)
            else:
                fav_ids.append(node_id)

            ui_cfg["favorite_node_ids"] = fav_ids
            context.save_ui_config(ui_cfg)
            handler.send_json({"ok": True, "favorite_node_ids": fav_ids})
        except Exception as exc:
            send_api_error(handler, "configuration_failed", exc=exc, operation="favorite update")
        return True

    return False
