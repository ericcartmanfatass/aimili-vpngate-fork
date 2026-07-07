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
