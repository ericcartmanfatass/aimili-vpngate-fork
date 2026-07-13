from __future__ import annotations

import vpn_utils
from aimilivpn.system import manager_wiring as wiring
from aimilivpn.system.manager_callbacks import print_line
from aimilivpn.system.manager_config import bounded_int


def build_repository_runtime(ctx: object) -> None:
    ctx.repositories = wiring.build_repositories(
        ctx.runtime_paths,
        storage_backend=ctx.storage_backend,
        sqlite_db_path=ctx.sqlite_db_path,
    )
    ctx.node_repository = ctx.repositories.node_repository
    ctx.region_repository = ctx.repositories.region_repository
    ctx.quality_repository = ctx.repositories.quality_repository
    ctx.settings_repository = ctx.repositories.settings_repository
    ctx.manager_repository_runtime = wiring.build_repository_runtime(wiring.RepositoryRuntimeWiring(
        node_repository=ctx.node_repository,
        region_repository=ctx.region_repository,
        country_translations=vpn_utils.COUNTRY_TRANSLATIONS,
    ))
    ctx.repository_facade = ctx.manager_repository_runtime.facade
    ctx.read_nodes = ctx.manager_repository_runtime.read_nodes
    ctx.write_nodes = ctx.manager_repository_runtime.write_nodes
    ctx.read_regions = ctx.manager_repository_runtime.read_regions
    ctx.region_from_payload = ctx.manager_repository_runtime.region_from_payload
    ctx.filter_nodes_by_region = ctx.manager_repository_runtime.filter_nodes_by_region
    ctx.region_target_id = ctx.manager_repository_runtime.region_target_id
    ctx.get_region_routing_target = ctx.manager_repository_runtime.get_region_routing_target
    ctx.routing_target_label = ctx.manager_repository_runtime.routing_target_label
    ctx.node_matches_country_target = ctx.manager_repository_runtime.node_matches_country_target
    ctx.node_matches_routing_region = ctx.manager_repository_runtime.node_matches_routing_region
    ctx.filter_nodes_by_routing_region = ctx.manager_repository_runtime.filter_nodes_by_routing_region
    ctx.validate_routing_region_target = ctx.manager_repository_runtime.validate_routing_region_target


def build_quality_runtime(ctx: object) -> None:
    ctx.manager_quality_runtime = wiring.build_quality_runtime(wiring.QualityRuntimeWiring(
        app_config=ctx.app_config,
        quality_repository=ctx.quality_repository,
        region_repository=ctx.region_repository,
        region_target_id=lambda target: ctx.region_target_id(target),
        read_nodes=lambda: ctx.read_nodes(),
        node_allowed=lambda node: ctx.node_matches_allowed_countries(node),
        bounded_int=bounded_int,
        test_multiple_nodes=lambda node_ids: ctx.test_multiple_nodes(node_ids),
    ))
    ctx.get_scamalytics_provider = ctx.manager_quality_runtime.get_scamalytics_provider
    ctx.latest_quality_for_node = ctx.manager_quality_runtime.latest_quality_for_node
    ctx.latest_quality_map = ctx.manager_quality_runtime.latest_quality_map
    ctx.check_quality_region = ctx.manager_quality_runtime.check_quality_region
    ctx.quality_provider_status = ctx.manager_quality_runtime.quality_provider_status


def build_shared_state(ctx: object) -> None:
    ctx.shared_state = wiring.build_shared_state()
    ctx.lock = ctx.shared_state.lock
    ctx.maintenance_lock = ctx.shared_state.maintenance_lock
    ctx.mutable_state = ctx.shared_state.mutable_state
    ctx.active_sessions = ctx.shared_state.active_sessions


def build_auth_runtime(ctx: object) -> None:
    ctx.manager_auth_runtime = wiring.build_auth_runtime()
    ctx.get_session_token = ctx.manager_auth_runtime.get_session_token


def build_ui_runtime(ctx: object) -> None:
    ctx.manager_ui_runtime = wiring.build_ui_runtime(wiring.UiRuntimeWiring(
        data_dir=lambda: ctx.data_dir,
        lock=ctx.lock,
        ui_host=lambda: ctx.ui_host,
        ui_port=lambda: ctx.ui_port,
        proxy_port=lambda: ctx.local_proxy_port,
        bounded_int=bounded_int,
    ))
    ctx.generate_random_password = ctx.manager_ui_runtime.generate_random_password
    ctx.generate_random_username = ctx.manager_ui_runtime.generate_random_username
    ctx.ui_config_store = ctx.manager_ui_runtime.store
    ctx.load_ui_config = ctx.manager_ui_runtime.load
    ctx.save_ui_config = ctx.manager_ui_runtime.save


def apply_saved_ui_overrides(ctx: object) -> None:
    ctx.ui_endpoints = wiring.apply_saved_ui_overrides(
        ctx.manager_ui_runtime,
        ctx.ui_host,
        ctx.ui_port,
        ctx.local_proxy_port,
    )
    ctx.ui_host = ctx.ui_endpoints.ui_host
    ctx.ui_port = ctx.ui_endpoints.ui_port
    ctx.local_proxy_port = ctx.ui_endpoints.local_proxy_port


def build_runtime_state(ctx: object) -> None:
    ctx.manager_runtime_state = wiring.build_runtime_state(wiring.RuntimeStateWiring(
        state_file=lambda: ctx.state_file,
        lock=ctx.lock,
        mutable_state=ctx.mutable_state,
        load_ui_config=lambda: ctx.load_ui_config(),
        api_url=lambda: ctx.api_url,
        instance_id=lambda: ctx.instance_id,
        tun_dev=lambda: ctx.tun_dev,
        policy_table=lambda: ctx.policy_table,
        allowed_countries=lambda: ctx.allowed_countries,
        target_valid_nodes=lambda: ctx.target_valid_nodes,
        fetch_interval_seconds=lambda: ctx.fetch_interval_seconds,
        check_interval_seconds=lambda: ctx.check_interval_seconds,
        local_proxy_host=lambda: ctx.local_proxy_host,
        local_proxy_port=lambda: ctx.local_proxy_port,
    ))
    ctx.write_json = ctx.manager_runtime_state.write_json
    ctx.read_json = ctx.manager_runtime_state.read_json
    ctx.runtime_state_store = ctx.manager_runtime_state.store
    ctx.set_state = ctx.manager_runtime_state.set_state
    ctx.set_connection_phase = ctx.manager_runtime_state.set_connection_phase
    ctx.get_state = ctx.manager_runtime_state.get_state


def build_runtime_files(ctx: object) -> None:
    ctx.manager_runtime_files = wiring.build_runtime_files(wiring.RuntimeFilesWiring(
        paths=lambda: ctx.runtime_paths,
        auth_user=lambda: ctx.openvpn_auth_user,
        auth_pass=lambda: ctx.openvpn_auth_pass,
        get_upstream_proxy_auth=vpn_utils.get_upstream_proxy_auth,
        print_line=print_line,
    ))
    ctx.ensure_dirs = ctx.manager_runtime_files.ensure_dirs
    ctx.upstream_proxy_auth_file = ctx.manager_runtime_files.upstream_proxy_auth_file
    ctx.write_ovpn_config = ctx.manager_runtime_files.write_ovpn_config
