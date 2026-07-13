function qualityBadgeHtml(node) {
  const score = Number(node.quality_score ?? 0);
  const label = node.quality_label || (score ? "Scored" : "");
  const nodeId = node.id || "";
  if (!score && !label) {
    return `<button type="button" class="badge not_checked quality-badge" data-action="open-quality" data-node-id="${esc(nodeId)}">未评分</button>`;
  }
  let badgeClass = "not_checked";
  if (score >= 70) {
    badgeClass = "available";
  } else if (score > 0 && score < 40) {
    badgeClass = "unavailable";
  }
  const titleParts = Array.isArray(node.quality_reasons) ? node.quality_reasons : [];
  const title = titleParts.length ? titleParts.join(", ") : label;
  return `<button type="button" class="badge ${badgeClass} quality-badge" title="${esc(title)}" data-action="open-quality" data-node-id="${esc(nodeId)}">${Number.isFinite(Number(score)) ? Number(score) : "-"} · ${esc(label || "Unknown")}</button>`;
}

function formatQualityBool(value) {
  if (value === true) return "是";
  if (value === false) return "否";
  return "-";
}

function formatQualityValue(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "-";
  return `${esc(value)}${suffix}`;
}

function renderQualityDetails(node, quality) {
  const score = quality && quality.score !== null && quality.score !== undefined
    ? quality.score
    : (node && node.quality_score) || "-";
  const label = quality && quality.label ? quality.label : (node && node.quality_label) || "Unknown";
  const reasons = quality && Array.isArray(quality.reasons)
    ? quality.reasons
    : (node && Array.isArray(node.quality_reasons) ? node.quality_reasons : []);
  const checkedAt = quality && quality.checked_at ? quality.checked_at : (node && node.quality_checked_at) || "";
  const riskProvider = quality && quality.risk_provider ? quality.risk_provider : "";
  const scamStatus = riskProvider === "scamalytics"
    ? "Scamalytics"
    : (quality && ((quality.risk_score !== null && quality.risk_score !== undefined) || quality.risk_level)
      ? "Other provider"
      : "Not checked");
  const nodeId = node && node.id ? node.id : "";
  const isTesting = Boolean(nodeId && testingNodeIds.has(nodeId));
  const reasonHtml = reasons.length
    ? reasons.map(reason => `<span class="region-code">${esc(reason)}</span>`).join("")
    : `<span class="badge not_checked">暂无原因明细</span>`;

  return `
    <div class="quality-summary">
      <div class="quality-score-panel">
        <div class="quality-detail-label">Score</div>
        <div class="quality-score-value">${esc(score)}</div>
        <div style="margin-top: 10px;">${qualityBadgeHtml({
          id: node ? node.id : "",
          quality_score: Number(score) || 0,
          quality_label: label,
          quality_reasons: reasons,
        })}</div>
        <div class="quality-detail-value mono" style="margin-top: 12px;">${esc(node ? node.id : "-")}</div>
      </div>
      <div class="quality-detail-panel">
        <div class="quality-detail-grid">
          <div class="quality-detail-item">
            <div class="quality-detail-label">Checked</div>
            <div class="quality-detail-value">${checkedAt ? esc(new Date(checkedAt).toLocaleString()) : "-"}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">TCP Latency</div>
            <div class="quality-detail-value">${formatQualityValue(quality && quality.tcp_latency_ms, " ms")}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">OpenVPN</div>
            <div class="quality-detail-value">${formatQualityBool(quality && quality.openvpn_success)}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">Handshake</div>
            <div class="quality-detail-value">${formatQualityValue(quality && quality.handshake_ms, " ms")}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">Risk Source</div>
            <div class="quality-detail-value">${esc(scamStatus)}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">Risk Score</div>
            <div class="quality-detail-value">${formatQualityValue(quality && quality.risk_score)}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">Risk Level</div>
            <div class="quality-detail-value">${formatQualityValue(quality && quality.risk_level)}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">Proxy</div>
            <div class="quality-detail-value">${formatQualityBool(quality && quality.proxy_detected)}</div>
          </div>
          <div class="quality-detail-item">
            <div class="quality-detail-label">Datacenter</div>
            <div class="quality-detail-value">${formatQualityBool(quality && quality.datacenter_detected)}</div>
          </div>
        </div>
        <div class="quality-reasons">${reasonHtml}</div>
      </div>
    </div>
    <div class="quality-actions">
      <button type="button" class="quality-action-btn" data-action="recheck-quality" data-node-id="${esc(nodeId)}" ${!nodeId || isTesting ? "disabled" : ""}>
        ${isTesting ? "Checking..." : "Recheck"}
      </button>
      <div class="quality-action-note">${riskProvider === "scamalytics" ? "Scamalytics risk data is included in this result." : "Local probe data is shown; Scamalytics is added when configured and reachable."}</div>
    </div>
  `;
}
