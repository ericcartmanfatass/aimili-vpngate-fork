from __future__ import annotations

import urllib.parse
from http import HTTPStatus
from typing import Any

from aimilivpn.core.regions import InvalidRegion, preview_region
from aimilivpn.web.api_errors import send_api_error, send_client_error
from aimilivpn.web.api import quality_to_dict, region_to_dict
from aimilivpn.web.route_contexts import RegionQualityRouteContext

def handle_region_quality_get(handler: Any, effective_path: str, context: RegionQualityRouteContext) -> bool:
    if effective_path == "/api/regions":
        handler.send_json({"regions": [region_to_dict(region) for region in context.read_regions()]})
        return True

    if effective_path.startswith("/api/regions/"):
        parts = effective_path.strip("/").split("/")
        if len(parts) != 3:
            handler.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return True
        region = context.region_repository.get(parts[2])
        if region is None:
            handler.send_json({"error": "region not found"}, HTTPStatus.NOT_FOUND)
            return True
        handler.send_json({"region": region_to_dict(region)})
        return True

    if effective_path == "/api/quality/providers":
        handler.send_json({"ok": True, **context.quality_provider_status()})
        return True

    if effective_path == "/api/quality":
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
        node_id = str((query.get("node_id") or [""])[0]).strip()
        if node_id:
            quality = context.latest_quality_for_node(node_id)
            if quality is None:
                handler.send_json({"ok": False, "error": "quality result not found"}, HTTPStatus.NOT_FOUND)
                return True
            handler.send_json({"ok": True, "quality": quality_to_dict(quality)})
            return True

        qualities = [
            quality_to_dict(result)
            for result in context.latest_quality_map().values()
        ]
        handler.send_json({"ok": True, "qualities": qualities})
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
            send_client_error(handler, "invalid_region", str(exc))
        except Exception as exc:
            send_api_error(handler, "region_operation_failed", exc=exc, operation="region create")
        return True

    if effective_path.startswith("/api/regions/"):
        parts = effective_path.strip("/").split("/")
        if len(parts) == 4 and parts[3] == "preview":
            try:
                region = context.region_repository.get(parts[2])
                if region is None:
                    handler.send_json({"ok": False, "error": "region not found"}, HTTPStatus.NOT_FOUND)
                    return True
                preview = preview_region(region, context.read_nodes(), context.latest_quality_map())
                handler.send_json({"ok": True, "preview": preview.__dict__})
            except (InvalidRegion, ValueError) as exc:
                send_client_error(handler, "invalid_region", str(exc))
            except Exception as exc:
                send_api_error(handler, "region_operation_failed", exc=exc, operation="region preview")
            return True
        handler.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        return True

    if effective_path == "/api/quality/check-node":
        try:
            payload = handler.read_json_body()
            node_id = str(payload.get("id") or payload.get("node_id") or "").strip()
            if not node_id:
                handler.send_json({"ok": False, "error": "node_id is required"}, HTTPStatus.BAD_REQUEST)
                return True
            updated_node = context.test_node_by_id(node_id)
            quality = context.latest_quality_for_node(node_id)
            handler.send_json({"ok": True, "node": updated_node, "quality": quality_to_dict(quality)})
        except ValueError as exc:
            send_client_error(handler, "node_not_found", str(exc), HTTPStatus.NOT_FOUND)
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="quality node check")
        return True

    if effective_path == "/api/quality/check-ip":
        try:
            payload = handler.read_json_body()
            ip = str(payload.get("ip") or "").strip()
            result = context.check_quality_ip(ip)
            handler.send_json({"ok": True, "quality": quality_to_dict(result)})
        except ValueError as exc:
            send_client_error(handler, "invalid_quality_request", str(exc))
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
            handler.send_json({"ok": True, **context.check_quality_region(region_id, limit=limit)})
        except ValueError as exc:
            send_client_error(handler, "invalid_quality_request", str(exc))
        except KeyError:
            handler.send_json({"ok": False, "error": "region not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            send_api_error(handler, "region_operation_failed", exc=exc, operation="quality region check")
        return True

    return False

def handle_region_put(handler: Any, effective_path: str, context: RegionQualityRouteContext) -> bool:
    if not effective_path.startswith("/api/regions"):
        return False

    parts = effective_path.strip("/").split("/")
    if len(parts) != 3 or parts[:2] != ["api", "regions"]:
        handler.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        return True

    region_id = parts[2]
    try:
        existing = context.region_repository.get(region_id)
        if existing is None:
            handler.send_json({"ok": False, "error": "region not found"}, HTTPStatus.NOT_FOUND)
            return True
        payload = handler.read_json_body()
        payload["id"] = region_id
        region = context.region_from_payload(payload, existing)
        context.region_repository.update(region_id, region_to_dict(region))
        saved_region = context.region_repository.get(region_id) or region
        handler.send_json({"ok": True, "region": region_to_dict(saved_region)})
    except (InvalidRegion, ValueError) as exc:
        send_client_error(handler, "invalid_region", str(exc))
    except KeyError:
        handler.send_json({"ok": False, "error": "region not found"}, HTTPStatus.NOT_FOUND)
    except Exception as exc:
        send_api_error(handler, "region_operation_failed", exc=exc, operation="region update")
    return True

def handle_region_delete(handler: Any, effective_path: str, context: RegionQualityRouteContext) -> bool:
    if not effective_path.startswith("/api/regions"):
        return False

    parts = effective_path.strip("/").split("/")
    if len(parts) != 3 or parts[:2] != ["api", "regions"]:
        handler.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        return True

    try:
        context.region_repository.delete(parts[2])
        handler.send_json({"ok": True})
    except KeyError:
        handler.send_json({"ok": False, "error": "region not found"}, HTTPStatus.NOT_FOUND)
    except Exception as exc:
        send_api_error(handler, "region_operation_failed", exc=exc, operation="region delete")
    return True
