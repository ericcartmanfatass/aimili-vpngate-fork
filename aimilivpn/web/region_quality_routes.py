from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.core.regions import InvalidRegion, preview_region
from aimilivpn.web.api_contract import InvalidListQuery, parse_list_query
from aimilivpn.web.api_errors import send_api_error, send_client_error
from aimilivpn.web.api import quality_to_dict, region_to_dict
from aimilivpn.web.operations import OperationCapacityError
from aimilivpn.web.route_contexts import RegionQualityRouteContext

def handle_region_quality_get(handler: Any, effective_path: str, context: RegionQualityRouteContext) -> bool:
    if effective_path == "/api/regions":
        try:
            query = parse_list_query(
                handler,
                allowed_filters=("enabled",),
                allowed_sort=("id", "name"),
                default_sort="id",
                default_limit=100,
            )
        except InvalidListQuery:
            send_client_error(handler, "invalid_query", "地区质量列表查询参数无效。")
            return True
        regions = [region_to_dict(region) for region in context.read_regions()]
        enabled = query.filters.get("enabled", "").lower()
        if enabled:
            if enabled not in {"true", "false"}:
                send_client_error(handler, "invalid_query", "地区质量列表查询参数无效。")
                return True
            regions = [region for region in regions if bool(region.get("enabled")) is (enabled == "true")]
        regions.sort(key=lambda region: str(region.get(query.sort) or "").lower(), reverse=query.order == "desc")
        page, pagination = query.page(regions)
        handler.send_json({"regions": page, "pagination": pagination})
        return True

    if effective_path.startswith("/api/regions/"):
        parts = effective_path.strip("/").split("/")
        if len(parts) != 3:
            handler.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
            return True
        region = context.region_repository.get(parts[2])
        if region is None:
            handler.send_json({"error": "地区不存在"}, HTTPStatus.NOT_FOUND)
            return True
        handler.send_json({"region": region_to_dict(region)})
        return True

    if effective_path == "/api/quality/providers":
        handler.send_json({"ok": True, **context.quality_provider_status()})
        return True

    if effective_path == "/api/quality":
        try:
            query = parse_list_query(
                handler,
                allowed_filters=("node_id", "provider", "label"),
                allowed_sort=("checked_at", "score", "risk_score", "node_id"),
                default_sort="checked_at",
                default_order="desc",
                default_limit=100,
            )
        except InvalidListQuery:
            send_client_error(handler, "invalid_query", "地区质量列表查询参数无效。")
            return True
        node_id = query.filters.get("node_id", "")
        if node_id:
            quality = context.latest_quality_for_node(node_id)
            if quality is None:
                handler.send_json({"ok": False, "error": "质量结果不存在"}, HTTPStatus.NOT_FOUND)
                return True
            handler.send_json({"ok": True, "quality": quality_to_dict(quality)})
            return True

        qualities = [
            quality_to_dict(result)
            for result in context.latest_quality_map().values()
        ]
        provider = query.filters.get("provider", "")
        label = query.filters.get("label", "")
        if provider:
            qualities = [item for item in qualities if item and str(item.get("risk_provider") or "") == provider]
        if label:
            qualities = [item for item in qualities if item and str(item.get("label") or "") == label]
        qualities.sort(
            key=lambda item: _quality_sort_value(item or {}, query.sort),
            reverse=query.order == "desc",
        )
        page, pagination = query.page(qualities)
        handler.send_json({"ok": True, "qualities": page, "pagination": pagination})
        return True

    return False

def handle_region_quality_post(handler: Any, effective_path: str, context: RegionQualityRouteContext) -> bool:
    if effective_path == "/api/regions":
        try:
            payload = handler.read_json_body()
            region = context.region_from_payload(payload)
            context.region_repository.create(region)
            saved_region = context.region_repository.get(region.id) or region
            handler.send_json({"ok": True, "region": region_to_dict(saved_region)}, HTTPStatus.CREATED)
        except (InvalidRegion, ValueError) as exc:
            send_client_error(handler, "invalid_region", "地区配置无效。")
        except Exception as exc:
            send_api_error(handler, "region_operation_failed", exc=exc, operation="region create")
        return True

    if effective_path.startswith("/api/regions/"):
        parts = effective_path.strip("/").split("/")
        if len(parts) == 4 and parts[3] == "preview":
            try:
                region = context.region_repository.get(parts[2])
                if region is None:
                    handler.send_json({"ok": False, "error": "地区不存在"}, HTTPStatus.NOT_FOUND)
                    return True
                preview = preview_region(region, context.read_nodes(), context.latest_quality_map())
                handler.send_json({"ok": True, "preview": preview.__dict__})
            except (InvalidRegion, ValueError) as exc:
                send_client_error(handler, "invalid_region", "地区配置无效。")
            except Exception as exc:
                send_api_error(handler, "region_operation_failed", exc=exc, operation="region preview")
            return True
        handler.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
        return True

    if effective_path == "/api/quality/check-node":
        try:
            payload = handler.read_json_body()
            node_id = str(payload.get("id") or payload.get("node_id") or "").strip()
            if not node_id:
                handler.send_json({"ok": False, "error": "必须提供节点 ID。"}, HTTPStatus.BAD_REQUEST)
                return True
            if context.submit_operation is not None:
                return _submit_quality_operation(
                    handler,
                    context,
                    "quality_check_node",
                    node_id,
                    lambda: {
                        "node": context.test_node_by_id(node_id),
                        "quality": quality_to_dict(context.latest_quality_for_node(node_id)),
                    },
                )
            updated_node = context.test_node_by_id(node_id)
            quality = context.latest_quality_for_node(node_id)
            handler.send_json({"ok": True, "node": updated_node, "quality": quality_to_dict(quality)})
        except ValueError as exc:
            send_client_error(handler, "node_not_found", "节点不存在", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="quality node check")
        return True

    if effective_path == "/api/quality/check-ip":
        try:
            payload = handler.read_json_body()
            ip = str(payload.get("ip") or "").strip()
            if not ip:
                raise ValueError("必须提供 IP 地址")
            if context.submit_operation is not None:
                return _submit_quality_operation(
                    handler,
                    context,
                    "quality_check_ip",
                    ip,
                    lambda: {"quality": quality_to_dict(context.check_quality_ip(ip))},
                )
            result = context.check_quality_ip(ip)
            handler.send_json({"ok": True, "quality": quality_to_dict(result)})
        except ValueError as exc:
            send_client_error(handler, "invalid_quality_request", "质量检测请求无效。")
        except context.scamalytics_errors as exc:
            send_api_error(
                handler,
                "quality_provider_failed",
                HTTPStatus.BAD_GATEWAY,
                exc=exc,
                operation="quality provider check",
            )
        except Exception as exc:
            send_api_error(handler, "quality_provider_failed", exc=exc, operation="quality IP check")
        return True

    if effective_path == "/api/quality/check-region":
        try:
            payload = handler.read_json_body()
            region_id = str(payload.get("id") or payload.get("region_id") or "").strip()
            limit = context.bounded_int(payload.get("limit"), 20, 1, 100)
            if context.submit_operation is not None:
                return _submit_quality_operation(
                    handler,
                    context,
                    "quality_check_region",
                    f"{region_id}:{limit}",
                    lambda: context.check_quality_region(region_id, limit=limit),
                )
            handler.send_json({"ok": True, **context.check_quality_region(region_id, limit=limit)})
        except ValueError as exc:
            send_client_error(handler, "invalid_quality_request", "质量检测请求无效。")
        except KeyError:
            handler.send_json({"ok": False, "error": "地区不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            send_api_error(handler, "region_operation_failed", exc=exc, operation="quality region check")
        return True

    return False

def handle_region_put(handler: Any, effective_path: str, context: RegionQualityRouteContext) -> bool:
    if not effective_path.startswith("/api/regions"):
        return False

    parts = effective_path.strip("/").split("/")
    if len(parts) != 3 or parts[:2] != ["api", "regions"]:
        handler.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
        return True

    region_id = parts[2]
    try:
        existing = context.region_repository.get(region_id)
        if existing is None:
            handler.send_json({"ok": False, "error": "地区不存在"}, HTTPStatus.NOT_FOUND)
            return True
        payload = handler.read_json_body()
        payload["id"] = region_id
        region = context.region_from_payload(payload, existing)
        context.region_repository.update(region_id, region_to_dict(region))
        saved_region = context.region_repository.get(region_id) or region
        handler.send_json({"ok": True, "region": region_to_dict(saved_region)})
    except (InvalidRegion, ValueError) as exc:
        send_client_error(handler, "invalid_region", "地区配置无效。")
    except KeyError:
        handler.send_json({"ok": False, "error": "地区不存在"}, HTTPStatus.NOT_FOUND)
    except Exception as exc:
        send_api_error(handler, "region_operation_failed", exc=exc, operation="region update")
    return True

def handle_region_delete(handler: Any, effective_path: str, context: RegionQualityRouteContext) -> bool:
    if not effective_path.startswith("/api/regions"):
        return False

    parts = effective_path.strip("/").split("/")
    if len(parts) != 3 or parts[:2] != ["api", "regions"]:
        handler.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
        return True

    try:
        context.region_repository.delete(parts[2])
        handler.send_json({"ok": True})
    except KeyError:
        handler.send_json({"ok": False, "error": "地区不存在"}, HTTPStatus.NOT_FOUND)
    except Exception as exc:
        send_api_error(handler, "region_operation_failed", exc=exc, operation="region delete")
    return True


def _submit_quality_operation(
    handler: Any,
    context: RegionQualityRouteContext,
    kind: str,
    target: str,
    task: Any,
) -> bool:
    explicit_key = str(getattr(handler, "headers", {}).get("X-Idempotency-Key", "") or "").strip()
    if len(explicit_key) > 128:
        send_client_error(handler, "invalid_idempotency_key", "幂等键无效。")
        return True
    key = explicit_key or f"implicit:{kind}:{target}"
    assert context.submit_operation is not None
    try:
        operation, duplicate = context.submit_operation(kind, key, task, bool(explicit_key))
    except OperationCapacityError:
        send_client_error(handler, "operation_capacity", "操作队列已满，请稍后重试。", HTTPStatus.SERVICE_UNAVAILABLE)
        return True
    handler.send_json(
        {
            "ok": True,
            "operation_id": operation["id"],
            "operation": operation,
            "deduplicated": duplicate,
        },
        HTTPStatus.ACCEPTED,
    )
    return True


def _quality_sort_value(item: dict[str, Any], field: str) -> Any:
    value = item.get(field)
    if field in {"score", "risk_score"}:
        try:
            return int(value) if value is not None else -1
        except (TypeError, ValueError):
            return -1
    return str(value or "").lower()
