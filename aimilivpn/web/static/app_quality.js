function qualityBadgeHtml(node) {
  const score = Number(node.quality_score ?? 0);
  const label = node.quality_label || (score ? "Scored" : "");
  const nodeId = esc(node.id || "");
  if (!score && !label) {
    return `<span class="badge not_checked quality-badge" onclick="openQualityModal('${nodeId}', event)">未评分</span>`;
  }
  let badgeClass = "not_checked";
  if (score >= 70) {
    badgeClass = "available";
  } else if (score > 0 && score < 40) {
    badgeClass = "unavailable";
  }
  const titleParts = Array.isArray(node.quality_reasons) ? node.quality_reasons : [];
  const title = titleParts.length ? titleParts.join(", ") : label;
  return `<span class="badge ${badgeClass} quality-badge" title="${esc(title)}" onclick="openQualityModal('${nodeId}', event)">${score || "-"} · ${esc(label || "Unknown")}</span>`;
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
      <button type="button" class="quality-action-btn" onclick="recheckQualityFromModal('${esc(nodeId)}', event)" ${!nodeId || isTesting ? "disabled" : ""}>
        ${isTesting ? "Checking..." : "Recheck"}
      </button>
      <div class="quality-action-note">${riskProvider === "scamalytics" ? "Scamalytics risk data is included in this result." : "Local probe data is shown; Scamalytics is added when configured and reachable."}</div>
    </div>
  `;
}

async function openQualityModal(id, event) {
  if (event) event.stopPropagation();
  const modal = $("quality_modal");
  const body = $("quality_modal_body");
  const node = nodes.find(n => n && n.id === id);
  currentQualityModalNodeId = id;
  modal.style.display = "flex";
  body.innerHTML = `<div class="message-box">正在加载质量详情...</div>`;

  try {
    const response = await fetch(`./api/quality?node_id=${encodeURIComponent(id)}`);
    const result = await response.json();
    if (response.ok && result.ok && result.quality) {
      body.innerHTML = renderQualityDetails(node, result.quality);
      return;
    }
    if (node) {
      body.innerHTML = renderQualityDetails(node, null);
      return;
    }
    body.innerHTML = `<div class="message-box">暂无质量检测结果，请先点击该节点的“检测”。</div>`;
  } catch (e) {
    body.innerHTML = `<div class="message-box error">质量详情加载失败，请稍后重试。</div>`;
  }
}

function closeQualityModal() {
  $("quality_modal").style.display = "none";
  currentQualityModalNodeId = "";
}

function applyQualityCheckResult(id, result) {
  if (!result || !result.ok || !result.node) return null;
  const updatedNode = {
    ...result.node,
    quality_score: result.quality ? result.quality.score : result.node.quality_score,
    quality_label: result.quality ? result.quality.label : result.node.quality_label,
    quality_reasons: result.quality ? result.quality.reasons : result.node.quality_reasons,
    quality_checked_at: result.quality ? result.quality.checked_at : result.node.quality_checked_at,
  };
  const idx = nodes.findIndex(n => n && n.id === id);
  if (idx !== -1) {
    nodes[idx] = updatedNode;
  }
  return updatedNode;
}

function applyRegionQualityResult(result) {
  if (!result || !Array.isArray(result.nodes)) return;
  const qualities = result.qualities || {};
  result.nodes.forEach(updated => {
    if (!updated || !updated.id) return;
    const quality = qualities[updated.id] || null;
    const idx = nodes.findIndex(n => n && n.id === updated.id);
    const merged = {
      ...(idx !== -1 ? nodes[idx] : {}),
      ...updated,
      quality_score: quality ? quality.score : updated.quality_score,
      quality_label: quality ? quality.label : updated.quality_label,
      quality_reasons: quality ? quality.reasons : updated.quality_reasons,
      quality_checked_at: quality ? quality.checked_at : updated.quality_checked_at,
    };
    if (idx !== -1) {
      nodes[idx] = merged;
    }
  });
}

async function requestQualityCheck(id) {
  const response = await fetch("./api/quality/check-node", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: id })
  });
  return response.json();
}

async function testNode(btn, id, event){
  if (event) event.stopPropagation();
  testingNodeIds.add(id);
  render();
  
  try {
    const result = await requestQualityCheck(id);
    applyQualityCheckResult(id, result);
    return result;
  } catch (e) {
    return null;
  } finally {
    testingNodeIds.delete(id);
    render();
  }
}

async function recheckQualityFromModal(id, event) {
  if (event) event.stopPropagation();
  if (!id || testingNodeIds.has(id)) return;
  const body = $("quality_modal_body");
  const node = nodes.find(n => n && n.id === id);
  testingNodeIds.add(id);
  body.innerHTML = renderQualityDetails(node, null);
  render();

  let result = null;
  try {
    result = await requestQualityCheck(id);
    applyQualityCheckResult(id, result);
  } catch (e) {
    result = null;
  } finally {
    testingNodeIds.delete(id);
    render();
  }

  if (currentQualityModalNodeId !== id) return;

  if (result && result.ok) {
    const updatedNode = nodes.find(n => n && n.id === id);
    body.innerHTML = renderQualityDetails(updatedNode, result.quality || null);
  } else {
    const updatedNode = nodes.find(n => n && n.id === id);
    body.innerHTML = `
      ${renderQualityDetails(updatedNode, null)}
      <div class="message-box error" style="margin-top: 12px;">Quality check failed. Please try again later.</div>
    `;
  }
}
