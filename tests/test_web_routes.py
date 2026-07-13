from __future__ import annotations

import io
import json
from http import HTTPStatus
import unittest
from unittest.mock import patch

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.web.routes import (
    ApiGetRouteContext,
    ApiMutationRouteContext,
    ApiPostRouteContext,
    AuthRouteContext,
    ConfigRouteContext,
    LogsRouteContext,
    NodeRouteContext,
    PageRouteContext,
    ProxyRouteContext,
    RegionQualityRouteContext,
    StatusRouteContext,
    handle_api_get,
    handle_api_delete,
    handle_api_post,
    handle_api_put,
    handle_auth_post,
    handle_config_post,
    handle_logs_get,
    handle_node_get,
    handle_node_post,
    handle_page_get,
    handle_proxy_post,
    handle_region_delete,
    handle_region_put,
    handle_region_quality_get,
    handle_region_quality_post,
    handle_status_get,
    is_session_authorized,
    parse_cookie_header,
    redact_secret_path,
    resolve_secret_path_request,
)


class AuthSessionHelperTests(unittest.TestCase):
    def test_redact_secret_path_removes_secret_from_access_log_message(self) -> None:
        message = redact_secret_path('"GET /private123/api/status HTTP/1.1" 200 -', "private123")

        self.assertNotIn("private123", message)
        self.assertIn("/<secret-path>/api/status", message)

    def test_parse_cookie_header_keeps_valid_pairs(self) -> None:
        cookies = parse_cookie_header("theme=dark; session=token-1; flag; spaced = value ")

        self.assertEqual(cookies["theme"], "dark")
        self.assertEqual(cookies["session"], "token-1")
        self.assertEqual(cookies["spaced"], "value")
        self.assertNotIn("flag", cookies)

    def test_is_session_authorized_requires_unexpired_session(self) -> None:
        sessions = {"token-1": 110.0, "old": 90.0}

        self.assertTrue(is_session_authorized("session=token-1", sessions, 100.0))
        self.assertFalse(is_session_authorized("session=old", sessions, 100.0))
        self.assertFalse(is_session_authorized("session=missing", sessions, 100.0))
        self.assertFalse(is_session_authorized("theme=dark", sessions, 100.0))
        self.assertEqual(sessions, {"token-1": 110.0})

    def test_is_session_authorized_allows_trusted_request(self) -> None:
        self.assertTrue(is_session_authorized("", {}, 100.0, trusted=True))

    def test_resolve_secret_path_allows_trusted_request(self) -> None:
        result = resolve_secret_path_request("/api/nodes", "secret", trusted=True)

        self.assertEqual(result.effective_path, "/api/nodes")
        self.assertIsNone(result.status)

    def test_resolve_secret_path_redirects_secret_root(self) -> None:
        result = resolve_secret_path_request("/secret", "secret")

        self.assertEqual(result.status, HTTPStatus.FOUND)
        self.assertEqual(result.redirect_location, "/secret/")
        self.assertEqual(result.effective_path, "")

    def test_resolve_secret_path_maps_prefixed_request(self) -> None:
        result = resolve_secret_path_request("/secret/api/nodes", "secret")

        self.assertEqual(result.effective_path, "/api/nodes")
        self.assertIsNone(result.status)

    def test_resolve_secret_path_rejects_wrong_secret(self) -> None:
        result = resolve_secret_path_request("/wrong/api/nodes", "secret")

        self.assertEqual(result.status, HTTPStatus.NOT_FOUND)
        self.assertEqual(result.effective_path, "")

    def test_resolve_secret_path_allows_empty_secret(self) -> None:
        result = resolve_secret_path_request("/api/nodes", "")

        self.assertEqual(result.effective_path, "/api/nodes")
        self.assertIsNone(result.status)


class FakeHandler:
    def __init__(
        self,
        payload: dict[str, object] | None = None,
        path: str = "",
        headers: dict[str, str] | None = None,
        secure: bool = False,
    ) -> None:
        self.payload = payload or {}
        self.path = path
        self.headers = headers or {}
        self.responses: list[tuple[dict[str, object], HTTPStatus]] = []
        self.response_status: HTTPStatus | None = None
        self.response_headers: list[tuple[str, str]] = []
        self.wfile = io.BytesIO()
        self.secure = secure

    def is_secure_request(self) -> bool:
        return self.secure

    def read_json_body(self, max_bytes: int = 65536) -> dict[str, object]:
        return dict(self.payload)

    def read_request_body(self, max_bytes: int = 65536) -> bytes:
        return b""

    def send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.responses.append((payload, status))

    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.response_status = status
        self.response_headers.append(("Content-Type", content_type))
        self.wfile.write(body)

    def send_response(self, status: HTTPStatus) -> None:
        self.response_status = status

    def send_header(self, name: str, value: str) -> None:
        self.response_headers.append((name, value))

    def end_headers(self) -> None:
        pass


class PageRouteTests(unittest.TestCase):
    def page_context(self, authorized: bool) -> PageRouteContext:
        return PageRouteContext(
            is_authorized=lambda: authorized,
            login_html_fallback="<html>login fallback</html>",
            index_html_fallback="<html>index fallback</html>",
        )

    def test_unauthorized_root_serves_login(self) -> None:
        handler = FakeHandler()
        with patch("aimilivpn.web.page_routes.get_login_html", return_value="<html>login</html>"):
            handled = handle_page_get(handler, "/", self.page_context(False))

        self.assertTrue(handled)
        self.assertEqual(handler.response_status, HTTPStatus.OK)
        self.assertEqual(handler.wfile.getvalue(), b"<html>login</html>")

    def test_unauthorized_api_get_returns_unauthorized(self) -> None:
        handler = FakeHandler()

        handled = handle_page_get(handler, "/api/nodes", self.page_context(False))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(payload["error"], "Unauthorized")

    def test_authorized_root_serves_index(self) -> None:
        handler = FakeHandler()
        with patch("aimilivpn.web.page_routes.get_index_html", return_value="<html>index</html>"):
            handled = handle_page_get(handler, "/index.html", self.page_context(True))

        self.assertTrue(handled)
        self.assertEqual(handler.response_status, HTTPStatus.OK)
        self.assertEqual(handler.wfile.getvalue(), b"<html>index</html>")

    def test_authorized_static_serves_asset(self) -> None:
        handler = FakeHandler()
        with (
            patch("aimilivpn.web.page_routes.get_static_asset", return_value=b"body{}"),
            patch("aimilivpn.web.page_routes.guess_content_type", return_value="text/css; charset=utf-8"),
        ):
            handled = handle_page_get(handler, "/static/style.css", self.page_context(True))

        self.assertTrue(handled)
        self.assertEqual(handler.response_status, HTTPStatus.OK)
        self.assertEqual(handler.wfile.getvalue(), b"body{}")
        self.assertIn(("Content-Type", "text/css; charset=utf-8"), handler.response_headers)

    def test_authorized_non_page_path_is_not_handled(self) -> None:
        handler = FakeHandler()

        handled = handle_page_get(handler, "/api/nodes", self.page_context(True))

        self.assertFalse(handled)


class FakeRegionRepository:
    def __init__(self) -> None:
        self.regions: dict[str, RegionProfile] = {}

    def get(self, region_id: str) -> RegionProfile | None:
        return self.regions.get(region_id)

    def create(self, region: RegionProfile) -> None:
        self.regions[region.id] = region

    def update(self, region_id: str, payload: dict[str, object]) -> None:
        existing = self.regions[region_id]
        self.regions[region_id] = RegionProfile(
            id=region_id,
            name=str(payload.get("name") or existing.name),
            country_codes=list(payload.get("country_codes") or existing.country_codes),
            include_keywords=list(payload.get("include_keywords") or existing.include_keywords),
            exclude_keywords=list(payload.get("exclude_keywords") or existing.exclude_keywords),
            min_quality_score=payload.get("min_quality_score"),  # type: ignore[arg-type]
            max_risk_score=payload.get("max_risk_score"),  # type: ignore[arg-type]
            enabled=bool(payload.get("enabled", existing.enabled)),
        )

    def delete(self, region_id: str) -> None:
        if region_id not in self.regions:
            raise KeyError(region_id)
        del self.regions[region_id]


def sample_region(region_id: str = "jp") -> RegionProfile:
    return RegionProfile(
        id=region_id,
        name="Japan",
        country_codes=["JP"],
        include_keywords=[],
        exclude_keywords=[],
        min_quality_score=None,
        max_risk_score=None,
        enabled=True,
    )


def sample_quality(node_id: str = "jp_1") -> QualityResult:
    return QualityResult(
        node_id=node_id,
        exit_ip="203.0.113.1",
        tcp_latency_ms=80,
        openvpn_success=True,
        handshake_ms=None,
        risk_provider=None,
        risk_score=None,
        risk_level=None,
        proxy_detected=False,
        datacenter_detected=False,
        country_match=None,
        checked_at="2026-06-17T00:00:00Z",
        score=80,
        label="Usable",
    )


def build_context(repository: FakeRegionRepository) -> RegionQualityRouteContext:
    qualities = {"jp_1": sample_quality()}
    return RegionQualityRouteContext(
        region_repository=repository,
        read_regions=lambda: list(repository.regions.values()),
        read_nodes=lambda: [{"id": "jp_1", "country_short": "JP"}],
        region_from_payload=lambda payload, existing=None: RegionProfile(
            id=str(payload.get("id") or (existing.id if existing else "")),
            name=str(payload.get("name") or (existing.name if existing else "")),
            country_codes=list(payload.get("country_codes") or (existing.country_codes if existing else [])),
            include_keywords=list(payload.get("include_keywords") or []),
            exclude_keywords=list(payload.get("exclude_keywords") or []),
            min_quality_score=payload.get("min_quality_score"),  # type: ignore[arg-type]
            max_risk_score=payload.get("max_risk_score"),  # type: ignore[arg-type]
            enabled=bool(payload.get("enabled", True)),
        ),
        quality_provider_status=lambda: {"providers": [{"name": "local_probe"}]},
        latest_quality_for_node=lambda node_id: qualities.get(node_id),
        latest_quality_map=lambda: qualities,
        test_node_by_id=lambda node_id: {"id": node_id, "probe_status": "available"},
        check_quality_ip=lambda ip: sample_quality(None),  # type: ignore[arg-type]
        check_quality_region=lambda region_id, limit: {"region_id": region_id, "limit": limit},
        bounded_int=lambda value, default, min_value, max_value: int(value or default),
        scamalytics_errors=(RuntimeError,),
    )


def build_node_context(nodes: list[dict[str, object]]) -> NodeRouteContext:
    state: dict[str, object] = {"active_openvpn_node_id": "jp_1"}
    written_nodes: list[list[dict[str, object]]] = []
    started_threads: list[tuple[object, tuple[object, ...]]] = []
    tested_batches: list[object] = []
    stopped: list[bool] = []
    saved_configs: list[dict[str, object]] = []
    last_ping = {"value": 0.0}
    last_latency = {"value": 0}

    def write_nodes(updated: list[dict[str, object]]) -> None:
        written_nodes.append(updated)
        nodes[:] = updated

    context = NodeRouteContext(
        read_nodes=lambda: nodes,
        write_nodes=write_nodes,
        filter_nodes_by_region=lambda items, region_id: [
            item for item in items if item.get("country_short") == region_id.upper()
        ],
        get_state=lambda: state,
        set_state=lambda **updates: state.update(updates),
        get_active_node_id=lambda: str(state.get("active_openvpn_node_id") or ""),
        get_last_active_ping_time=lambda: last_ping["value"],
        set_last_active_ping_time=lambda value: last_ping.update(value=value),
        get_last_active_latency=lambda: last_latency["value"],
        set_last_active_latency=lambda value: last_latency.update(value=value),
        now=lambda: 20.0,
        ping_latency_ms=lambda ip, port, fallback: 88,
        parse_int=lambda value: int(value or 0),
        start_daemon_thread=lambda target, args: started_threads.append((target, args)),
        test_multiple_nodes=lambda ids: tested_batches.append(ids) or [{"id": "jp_1"}],
        test_node_by_id=lambda node_id: {"id": node_id, "probe_status": "available"},
        connect_node=lambda node_id: f"connected {node_id}",
        stop_active_openvpn=lambda: stopped.append(True),
        load_ui_config=lambda: {"connection_enabled": True},
        save_ui_config=lambda config: saved_configs.append(config),
        maintain_valid_nodes=lambda force: "maintained" if force else "started",
        maintenance_running=lambda: False,
        start_maintenance=lambda: started_threads.append(("maintenance", ())),
    )
    object.__setattr__(context, "_test_written_nodes", written_nodes)
    object.__setattr__(context, "_test_started_threads", started_threads)
    object.__setattr__(context, "_test_tested_batches", tested_batches)
    object.__setattr__(context, "_test_stopped", stopped)
    object.__setattr__(context, "_test_saved_configs", saved_configs)
    return context


def build_config_context(config: dict[str, object]) -> ConfigRouteContext:
    saved_configs: list[dict[str, object]] = []
    cleared_sessions: list[bool] = []
    restarts: list[str] = []
    validated_targets: list[tuple[str, str]] = []

    def save_config(updated: dict[str, object]) -> None:
        saved_configs.append(dict(updated))
        config.clear()
        config.update(updated)

    def validate_target(mode: str, target: str) -> None:
        validated_targets.append((mode, target))
        if target == "missing":
            raise ValueError("region not found")

    context = ConfigRouteContext(
        load_ui_config=lambda: dict(config),
        save_ui_config=save_config,
        validate_routing_region_target=validate_target,
        clear_sessions=lambda: cleared_sessions.append(True),
        schedule_restart=lambda message: restarts.append(message),
    )
    object.__setattr__(context, "_test_saved_configs", saved_configs)
    object.__setattr__(context, "_test_cleared_sessions", cleared_sessions)
    object.__setattr__(context, "_test_restarts", restarts)
    object.__setattr__(context, "_test_validated_targets", validated_targets)
    return context


def build_auth_context(config: dict[str, object]) -> AuthRouteContext:
    sessions: dict[str, float] = {}
    removed_sessions: list[str] = []

    context = AuthRouteContext(
        load_ui_config=lambda: dict(config),
        verify_password=lambda raw, expected: raw == "correct" and expected == config.get("password_hash"),
        verify_username=lambda raw, expected: raw == expected,
        generate_session_token=lambda: "token-1",
        add_session=lambda token, expires_at: sessions.update({token: expires_at}),
        remove_session=lambda token: removed_sessions.append(token),
        get_secret_path=lambda: "secret",
        now=lambda: 100.0,
    )
    object.__setattr__(context, "_test_sessions", sessions)
    object.__setattr__(context, "_test_removed_sessions", removed_sessions)
    return context


def build_proxy_context(result: dict[str, object]) -> ProxyRouteContext:
    states: list[dict[str, object]] = []

    context = ProxyRouteContext(
        check_proxy_health=lambda: dict(result),
        set_state=lambda **updates: states.append(updates),
    )
    object.__setattr__(context, "_test_states", states)
    return context


def build_status_context(
    *,
    proxy_ok: bool = True,
    active_openvpn: bool = True,
    active_node_id: str = "jp_1",
    tun_exists: bool = True,
) -> StatusRouteContext:
    return StatusRouteContext(
        load_ui_config=lambda: {"host": "127.0.0.1", "port": 8787},
        ui_host="::",
        ui_port=8787,
        proxy_host="127.0.0.1",
        proxy_port=7928,
        proxy_gateway_status=lambda: (proxy_ok, "" if proxy_ok else "connect failed"),
        active_openvpn_running=lambda: active_openvpn,
        active_node_id=lambda: active_node_id,
        is_linux=lambda: True,
        tun_dev="tun0",
        tun_exists=lambda: tun_exists,
        now=lambda: 200.0,
        server_start_time=100.0,
        last_collector_heartbeat=lambda: 190.0,
        last_checker_heartbeat=lambda: 195.0,
        last_pinger_heartbeat=lambda: 198.0,
        check_interval_seconds=1260,
        format_local_time=lambda value: f"ts:{int(value)}",
    )


def build_api_get_context(nodes: list[dict[str, object]] | None = None) -> ApiGetRouteContext:
    repository = FakeRegionRepository()
    return ApiGetRouteContext(
        region_quality=build_context(repository),
        node=build_node_context(nodes or []),
        status=build_status_context(),
        logs=LogsRouteContext(read_log_entries=lambda: [{"level": "INFO", "message": "ok"}]),
    )


def build_api_post_context(*, authorized: bool = True) -> ApiPostRouteContext:
    repository = FakeRegionRepository()
    return ApiPostRouteContext(
        auth=build_auth_context({"username": "admin", "password_hash": "hash"}),
        region_quality=build_context(repository),
        node=build_node_context([]),
        config=build_config_context({"username": "admin", "password_hash": "hash", "port": 8787, "proxy_port": 7928}),
        proxy=build_proxy_context({"ok": True, "ip": "198.51.100.1", "latency_ms": 42}),
        is_authorized=lambda: authorized,
    )


def build_api_mutation_context(repository: FakeRegionRepository, *, authorized: bool = True) -> ApiMutationRouteContext:
    return ApiMutationRouteContext(
        region_quality=build_context(repository),
        is_authorized=lambda: authorized,
    )


class WebRoutesTests(unittest.TestCase):
    def test_api_get_dispatches_nodes(self) -> None:
        handler = FakeHandler(path="/api/nodes")
        context = build_api_get_context([{"id": "jp_1", "country_short": "JP"}])

        handled = handle_api_get(handler, "/api/nodes", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["nodes"][0]["id"], "jp_1")  # type: ignore[index]

    def test_api_get_rejects_raw_configs(self) -> None:
        handler = FakeHandler()

        handled = handle_api_get(handler, "/configs/jp.ovpn", build_api_get_context())

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.FORBIDDEN)
        self.assertEqual(payload["error"], "raw OpenVPN configs are not exposed")

    def test_api_get_dispatches_logs(self) -> None:
        handler = FakeHandler()

        handled = handle_api_get(handler, "/api/logs", build_api_get_context())

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["logs"], [{"level": "INFO", "message": "ok"}])

    def test_api_get_returns_false_for_unknown_path(self) -> None:
        handler = FakeHandler()

        handled = handle_api_get(handler, "/missing", build_api_get_context())

        self.assertFalse(handled)
        self.assertEqual(handler.responses, [])

    def test_api_post_allows_login_without_existing_session(self) -> None:
        handler = FakeHandler({"username": "admin", "password": "correct"})
        context = build_api_post_context(authorized=False)

        handled = handle_api_post(handler, "/api/login", context)

        self.assertTrue(handled)
        self.assertEqual(handler.response_status, HTTPStatus.OK)
        self.assertEqual(json.loads(handler.wfile.getvalue().decode("utf-8")), {"ok": True})

    def test_api_post_rejects_unauthorized_protected_route(self) -> None:
        handler = FakeHandler({"ids": ["jp_1"]})

        handled = handle_api_post(handler, "/api/test_nodes", build_api_post_context(authorized=False))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(payload["error"], "Unauthorized")

    def test_api_post_dispatches_proxy_check(self) -> None:
        handler = FakeHandler()

        handled = handle_api_post(handler, "/api/test_proxy", build_api_post_context())

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["ip"], "198.51.100.1")

    def test_api_post_returns_not_found_for_unknown_path(self) -> None:
        handler = FakeHandler()

        handled = handle_api_post(handler, "/missing", build_api_post_context())

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.NOT_FOUND)
        self.assertEqual(payload["error"], "not found")

    def test_api_put_rejects_unauthorized_request(self) -> None:
        repository = FakeRegionRepository()
        handler = FakeHandler({"name": "Tokyo", "country_codes": ["JP"]})

        handled = handle_api_put(handler, "/api/regions/jp", build_api_mutation_context(repository, authorized=False))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(payload["error"], "Unauthorized")

    def test_api_put_dispatches_region_update(self) -> None:
        repository = FakeRegionRepository()
        repository.create(sample_region())
        handler = FakeHandler({"name": "Tokyo", "country_codes": ["JP"]})

        handled = handle_api_put(handler, "/api/regions/jp", build_api_mutation_context(repository))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["ok"])
        self.assertEqual(repository.get("jp").name, "Tokyo")  # type: ignore[union-attr]

    def test_api_delete_dispatches_region_delete(self) -> None:
        repository = FakeRegionRepository()
        repository.create(sample_region())
        handler = FakeHandler()

        handled = handle_api_delete(handler, "/api/regions/jp", build_api_mutation_context(repository))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["ok"])
        self.assertIsNone(repository.get("jp"))

    def test_api_delete_rejects_unauthorized_request(self) -> None:
        repository = FakeRegionRepository()
        repository.create(sample_region())
        handler = FakeHandler()

        handled = handle_api_delete(handler, "/api/regions/jp", build_api_mutation_context(repository, authorized=False))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(payload["error"], "Unauthorized")
        self.assertIsNotNone(repository.get("jp"))

    def test_api_delete_returns_not_found_for_unknown_path(self) -> None:
        repository = FakeRegionRepository()
        handler = FakeHandler()

        handled = handle_api_delete(handler, "/missing", build_api_mutation_context(repository))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.NOT_FOUND)
        self.assertEqual(payload["error"], "not found")

    def test_get_quality_by_node(self) -> None:
        repository = FakeRegionRepository()
        handler = FakeHandler(path="/api/quality?node_id=jp_1")

        handled = handle_region_quality_get(handler, "/api/quality", build_context(repository))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["quality"]["node_id"], "jp_1")  # type: ignore[index]

    def test_post_region_creates_region(self) -> None:
        repository = FakeRegionRepository()
        handler = FakeHandler({"id": "jp", "name": "Japan", "country_codes": ["JP"]})

        handled = handle_region_quality_post(handler, "/api/regions", build_context(repository))

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.CREATED)
        self.assertEqual(payload["region"]["id"], "jp")  # type: ignore[index]
        self.assertIsNotNone(repository.get("jp"))

    def test_put_and_delete_region(self) -> None:
        repository = FakeRegionRepository()
        repository.create(sample_region())
        context = build_context(repository)

        put_handler = FakeHandler({"name": "Tokyo", "country_codes": ["JP"]})
        self.assertTrue(handle_region_put(put_handler, "/api/regions/jp", context))
        self.assertEqual(repository.get("jp").name, "Tokyo")  # type: ignore[union-attr]

        delete_handler = FakeHandler()
        self.assertTrue(handle_region_delete(delete_handler, "/api/regions/jp", context))
        self.assertIsNone(repository.get("jp"))

    def test_get_nodes_marks_active_and_excludes_config_text(self) -> None:
        nodes = [
            {
                "id": "jp_1",
                "country_short": "JP",
                "ip": "203.0.113.1",
                "remote_port": 1194,
                "ping": 100,
                "config_text": "secret config",
            }
        ]
        context = build_node_context(nodes)
        handler = FakeHandler(path="/api/nodes")

        handled = handle_node_get(handler, "/api/nodes", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["nodes"][0]["active"])  # type: ignore[index]
        self.assertNotIn("config_text", payload["nodes"][0])  # type: ignore[index]
        self.assertEqual(len(context._test_started_threads), 1)  # type: ignore[attr-defined]

    def test_post_test_nodes_uses_payload_ids(self) -> None:
        context = build_node_context([])
        handler = FakeHandler({"ids": ["jp_1"]})

        handled = handle_node_post(handler, "/api/test_nodes", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["nodes"], [{"id": "jp_1"}])
        self.assertEqual(context._test_tested_batches, [["jp_1"]])  # type: ignore[attr-defined]

    def test_post_disconnect_disables_connection_and_clears_nodes(self) -> None:
        nodes = [{"id": "jp_1", "active": True}]
        context = build_node_context(nodes)
        handler = FakeHandler()

        handled = handle_node_post(handler, "/api/disconnect", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(nodes[0]["active"], False)
        self.assertEqual(context._test_saved_configs, [{"connection_enabled": False}])  # type: ignore[attr-defined]
        self.assertEqual(context._test_stopped, [True])  # type: ignore[attr-defined]

    def test_update_credentials_saves_and_requires_restart_on_port_change(self) -> None:
        config = {
            "username": "admin",
            "password_hash": "hash",
            "port": 8787,
            "secret_path": "oldpath",
        }
        context = build_config_context(config)
        handler = FakeHandler({
            "username": "newadmin",
            "password": "newpass",
            "port": 8788,
            "secret_path": "newpath",
        })

        handled = handle_config_post(handler, "/api/update_credentials", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["restart_needed"])
        self.assertTrue(payload["reauth_required"])
        self.assertEqual(config["username"], "newadmin")
        self.assertEqual(context._test_cleared_sessions, [True])  # type: ignore[attr-defined]
        self.assertEqual(len(context._test_restarts), 1)  # type: ignore[attr-defined]

    def test_update_credentials_revokes_sessions_on_secret_path_change(self) -> None:
        config = {
            "username": "admin",
            "password_hash": "hash",
            "port": 8787,
            "secret_path": "oldpath",
        }
        context = build_config_context(config)
        handler = FakeHandler({
            "username": "admin",
            "password": "",
            "port": 8787,
            "secret_path": "newpath",
        })

        handle_config_post(handler, "/api/update_credentials", context)

        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["reauth_required"])
        self.assertEqual(context._test_cleared_sessions, [True])  # type: ignore[attr-defined]

    def test_update_settings_rejects_invalid_region_target(self) -> None:
        config = {"port": 8787, "proxy_port": 7928}
        context = build_config_context(config)
        handler = FakeHandler({
            "proxy_port": 7929,
            "routing_mode": "fixed_region",
            "force_country": "missing",
            "routing_ip_type": "all",
        })

        handled = handle_config_post(handler, "/api/update_settings", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["error"], "region not found")
        self.assertEqual(context._test_saved_configs, [])  # type: ignore[attr-defined]

    def test_update_routing_saves_routing_fields(self) -> None:
        config = {"enable_force_country": True}
        context = build_config_context(config)
        handler = FakeHandler({
            "routing_mode": "favorites",
            "force_country": "",
            "routing_ip_type": "residential",
            "fav_fail_fallback": False,
        })

        handled = handle_config_post(handler, "/api/update_routing", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["ok"])
        self.assertEqual(config["routing_mode"], "favorites")
        self.assertEqual(config["routing_ip_type"], "residential")
        self.assertFalse(config["fav_fail_fallback"])
        self.assertNotIn("enable_force_country", config)

    def test_toggle_favorite_adds_and_removes_node_id(self) -> None:
        config = {"favorite_node_ids": ["jp_1"]}
        context = build_config_context(config)

        remove_handler = FakeHandler({"id": "jp_1"})
        self.assertTrue(handle_config_post(remove_handler, "/api/toggle_favorite", context))
        self.assertEqual(config["favorite_node_ids"], [])

        add_handler = FakeHandler({"id": "jp_2"})
        self.assertTrue(handle_config_post(add_handler, "/api/toggle_favorite", context))
        self.assertEqual(config["favorite_node_ids"], ["jp_2"])

    def test_login_sets_session_cookie(self) -> None:
        context = build_auth_context({"username": "admin", "password_hash": "hash"})
        handler = FakeHandler({"username": "admin", "password": "correct"})

        handled = handle_auth_post(handler, "/api/login", context)

        self.assertTrue(handled)
        self.assertEqual(handler.response_status, HTTPStatus.OK)
        self.assertEqual(json.loads(handler.wfile.getvalue().decode("utf-8")), {"ok": True})
        self.assertEqual(context._test_sessions, {"token-1": 100.0 + 30 * 24 * 3600})  # type: ignore[attr-defined]
        cookies = [value for name, value in handler.response_headers if name == "Set-Cookie"]
        self.assertEqual(len(cookies), 1)
        self.assertIn("session=token-1", cookies[0])
        self.assertIn("Path=/secret/", cookies[0])
        self.assertIn("HttpOnly", cookies[0])
        self.assertIn("SameSite=Lax", cookies[0])
        self.assertIn("Max-Age=2592000", cookies[0])

    def test_login_sets_secure_cookie_for_trusted_https_request(self) -> None:
        context = build_auth_context({"username": "admin", "password_hash": "hash"})
        handler = FakeHandler({"username": "admin", "password": "correct"}, secure=True)

        self.assertTrue(handle_auth_post(handler, "/api/login", context))

        cookies = [value for name, value in handler.response_headers if name == "Set-Cookie"]
        self.assertEqual(len(cookies), 1)
        self.assertIn("Secure", cookies[0])

    def test_login_rejects_invalid_credentials(self) -> None:
        context = build_auth_context({"username": "admin", "password_hash": "hash"})
        handler = FakeHandler({"username": "admin", "password": "wrong"})

        handled = handle_auth_post(handler, "/api/login", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.FORBIDDEN)
        self.assertFalse(payload["ok"])
        self.assertEqual(context._test_sessions, {})  # type: ignore[attr-defined]

    def test_logout_removes_session_and_clears_cookie(self) -> None:
        context = build_auth_context({"username": "admin", "password_hash": "hash"})
        handler = FakeHandler(headers={"Cookie": "theme=dark; session=old-token"})

        handled = handle_auth_post(handler, "/api/logout", context)

        self.assertTrue(handled)
        self.assertEqual(handler.response_status, HTTPStatus.OK)
        self.assertEqual(context._test_removed_sessions, ["old-token"])  # type: ignore[attr-defined]
        cookies = [value for name, value in handler.response_headers if name == "Set-Cookie"]
        self.assertEqual(len(cookies), 1)
        self.assertIn("session=;", cookies[0])
        self.assertIn("HttpOnly", cookies[0])
        self.assertIn("SameSite=Lax", cookies[0])
        self.assertIn("Max-Age=0", cookies[0])
        self.assertIn("Expires=Thu, 01 Jan 1970 00:00:00 GMT", cookies[0])

    def test_proxy_check_updates_success_state(self) -> None:
        context = build_proxy_context({"ok": True, "ip": "198.51.100.1", "latency_ms": 42})
        handler = FakeHandler()

        handled = handle_proxy_post(handler, "/api/test_proxy", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["ip"], "198.51.100.1")
        self.assertEqual(context._test_states, [{  # type: ignore[attr-defined]
            "proxy_ok": True,
            "proxy_ip": "198.51.100.1",
            "proxy_latency_ms": 42,
            "proxy_error": "",
        }])

    def test_proxy_check_updates_failure_state(self) -> None:
        context = build_proxy_context({"ok": False, "error": "timeout"})
        handler = FakeHandler()

        handled = handle_proxy_post(handler, "/api/test_proxy", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertFalse(payload["ok"])
        self.assertEqual(context._test_states, [{  # type: ignore[attr-defined]
            "proxy_ok": False,
            "proxy_ip": "-",
            "proxy_latency_ms": 0,
            "proxy_error": "timeout",
        }])

    def test_gateway_status_reports_services(self) -> None:
        handler = FakeHandler()

        handled = handle_status_get(handler, "/api/gateway_status", build_status_context())

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["ok"])
        services = {item["name"]: item for item in payload["services"]}  # type: ignore[index]
        self.assertEqual(services["Web 管理服务"]["status"], "running")
        self.assertEqual(services["本地代理网关"]["status"], "running")
        self.assertEqual(services["OpenVPN 核心连接"]["status"], "running")

    def test_gateway_status_reports_proxy_and_tun_warnings(self) -> None:
        handler = FakeHandler()

        handled = handle_status_get(
            handler,
            "/api/gateway_status",
            build_status_context(proxy_ok=False, active_openvpn=True, tun_exists=False),
        )

        self.assertTrue(handled)
        payload, _ = handler.responses[-1]
        services = {item["name"]: item for item in payload["services"]}  # type: ignore[index]
        self.assertEqual(services["本地代理网关"]["status"], "stopped")
        self.assertEqual(services["本地代理网关"]["error"], "connect failed")
        self.assertIn("虚拟网卡", services["OpenVPN 核心连接"]["error"])

    def test_logs_get_returns_entries(self) -> None:
        context = LogsRouteContext(read_log_entries=lambda: [{"level": "INFO", "message": "ok"}])
        handler = FakeHandler()

        handled = handle_logs_get(handler, "/api/logs", context)

        self.assertTrue(handled)
        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["logs"], [{"level": "INFO", "message": "ok"}])


if __name__ == "__main__":
    unittest.main()
