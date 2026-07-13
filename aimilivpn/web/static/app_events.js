function invokeUiAction(action, target, event) {
  const nodeId = target.dataset.nodeId || "";
  const regionId = target.dataset.regionId || "";
  const actions = {
    "open-credentials": () => openCredentialsModal(),
    "open-network": () => openNetworkModal(),
    "open-regions": () => openRegionsModal(),
    "open-gateway": () => openGatewayModal(),
    "open-logs": () => openLogsModal(),
    "open-vps": () => openVpsModal(),
    "close-regions": () => closeRegionsModal(),
    "reset-region": () => resetRegionForm(),
    "close-quality": () => closeQualityModal(),
    "close-credentials": () => closeCredentialsModal(),
    "close-network": () => closeNetworkModal(),
    "close-vps": () => closeVpsModal(),
    "close-gateway": () => closeGatewayModal(),
    "close-logs": () => closeLogsModal(),
    "logout": () => logoutAdmin(),
    "toggle-favorites": () => toggleFavoritesView(),
    "toggle-favorite-routing": () => toggleFavRouting(),
    "copy-logs": () => copyLogContent(),
    "export-logs": () => exportLogContent(),
    "set-routing-mode": () => setRoutingMode(target.dataset.value || ""),
    "set-routing-ip-type": () => setRoutingIpType(target.dataset.value || ""),
    "test-node": () => testNode(target, nodeId, event),
    "connect-node": () => connectNode(nodeId),
    "toggle-favorite": () => toggleFavorite(nodeId, event),
    "open-quality": () => openQualityModal(nodeId, event),
    "recheck-quality": () => recheckQualityFromModal(nodeId, event),
    "check-region": () => checkRegionQuality(regionId),
    "edit-region": () => editRegion(regionId),
    "preview-region": () => previewRegion(regionId),
    "select-region": () => selectRegionFromModal(regionId),
    "delete-region": () => deleteRegion(regionId),
    "disconnect-node": () => disconnectNode(),
  };
  const handler = actions[action];
  if (handler) handler();
}

document.addEventListener("click", event => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  event.preventDefault();
  invokeUiAction(target.dataset.action || "", target, event);
});

$("regions_form").addEventListener("submit", saveRegion);
$("credentials_form").addEventListener("submit", saveCredentials);
$("network_form").addEventListener("submit", saveNetwork);
$("fav_fail_fallback_checkbox").addEventListener("change", event => {
  handleFavFallbackChange(event.target.checked);
});
$("log_filter_select").addEventListener("change", filterAndRenderLogs);
