from __future__ import annotations

from aimilivpn.system.manager_entry import ManagerEntryRuntime
from aimilivpn.system.manager_node_probe import ManagerNodeProbeRuntime
from aimilivpn.system.manager_openvpn import ManagerOpenVPNRuntime
from aimilivpn.system.manager_service import ManagerServiceRuntime
from aimilivpn.system.manager_wiring_factory_common import build_runtime
from aimilivpn.system.manager_wiring_process_types import (
    EntryRuntimeWiring,
    NodeProbeRuntimeWiring,
    OpenVPNRuntimeWiring,
    ServiceRuntimeWiring,
)


def build_entry_runtime(wiring: EntryRuntimeWiring) -> ManagerEntryRuntime:
    return build_runtime(ManagerEntryRuntime, wiring)


def build_service_runtime(wiring: ServiceRuntimeWiring) -> ManagerServiceRuntime:
    return build_runtime(ManagerServiceRuntime, wiring)


def build_openvpn_runtime(wiring: OpenVPNRuntimeWiring) -> ManagerOpenVPNRuntime:
    return build_runtime(ManagerOpenVPNRuntime, wiring)


def build_node_probe_runtime(wiring: NodeProbeRuntimeWiring) -> ManagerNodeProbeRuntime:
    return build_runtime(ManagerNodeProbeRuntime, wiring)
