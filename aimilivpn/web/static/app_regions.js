function regionTextList(value) {
  return Array.isArray(value) ? value.join(", ") : "";
}

function setRegionsMessage(type, message) {
  const errorEl = $("regions_error");
  const successEl = $("regions_success");
  if (!errorEl || !successEl) return;
  errorEl.style.display = "none";
  successEl.style.display = "none";
  if (!message) return;
  const target = type === "error" ? errorEl : successEl;
  target.textContent = message;
  target.style.display = "block";
}

function renderRegionsList() {
  const list = $("regions_list");
  if (!list) return;
  if (!regions.length) {
    list.innerHTML = `<div style="color: var(--text-secondary); padding: 18px; text-align: center;">暂无地区配置</div>`;
    return;
  }
  list.innerHTML = regions.map(region => {
    const isActive = selectedRegionId && selectedRegionId === region.id;
    const isChecking = checkingRegionIds.has(region.id);
    const codes = (region.country_codes || []).map(code => `<span class="region-code">${esc(code)}</span>`).join("");
    const enabledBadge = region.enabled
      ? `<span class="badge available">启用</span>`
      : `<span class="badge unavailable">停用</span>`;
    return `
      <div class="region-item ${isActive ? "active" : ""}">
        <div class="region-item-head">
          <div>
            <div class="region-name">${esc(region.name)}</div>
            <div class="region-id">${esc(region.id)}</div>
          </div>
          ${enabledBadge}
        </div>
        <div class="region-codes">${codes}</div>
        <div class="region-actions">
          <button type="button" class="test-btn" onclick="checkRegionQuality('${esc(region.id)}')" ${isChecking ? "disabled" : ""}>${isChecking ? "Checking..." : "Check"}</button>
          <button type="button" class="test-btn" onclick="editRegion('${esc(region.id)}')">编辑</button>
          <button type="button" class="test-btn" onclick="previewRegion('${esc(region.id)}')">预览</button>
          <button type="button" class="connect-btn" onclick="selectRegionFromModal('${esc(region.id)}')">筛选</button>
          <button type="button" class="test-btn" style="color: var(--danger); border-color: rgba(244, 63, 94, 0.35);" onclick="deleteRegion('${esc(region.id)}')">删除</button>
        </div>
      </div>
    `;
  }).join("");
}

function resetRegionForm() {
  const form = $("regions_form");
  if (form) form.reset();
  $("region_editing_id").value = "";
  $("region_id").disabled = false;
  $("region_enabled").checked = true;
  $("regions_submit_btn").textContent = "保存地区";
  $("regions_preview").innerHTML = "";
  setRegionsMessage("", "");
}

function editRegion(id) {
  const region = regions.find(item => item.id === id);
  if (!region) return;
  $("region_editing_id").value = region.id;
  $("region_id").value = region.id;
  $("region_id").disabled = true;
  $("region_name").value = region.name || "";
  $("region_country_codes").value = regionTextList(region.country_codes);
  $("region_include_keywords").value = regionTextList(region.include_keywords);
  $("region_exclude_keywords").value = regionTextList(region.exclude_keywords);
  $("region_min_quality").value = region.min_quality_score ?? "";
  $("region_max_risk").value = region.max_risk_score ?? "";
  $("region_enabled").checked = region.enabled !== false;
  $("regions_submit_btn").textContent = "更新地区";
  $("regions_preview").innerHTML = "";
  setRegionsMessage("", "");
}

function regionPayloadFromForm() {
  const minQuality = $("region_min_quality").value.trim();
  const maxRisk = $("region_max_risk").value.trim();
  return {
    id: $("region_id").value.trim(),
    name: $("region_name").value.trim(),
    country_codes: $("region_country_codes").value.trim(),
    include_keywords: $("region_include_keywords").value.trim(),
    exclude_keywords: $("region_exclude_keywords").value.trim(),
    min_quality_score: minQuality === "" ? null : Number(minQuality),
    max_risk_score: maxRisk === "" ? null : Number(maxRisk),
    enabled: $("region_enabled").checked,
  };
}

async function saveRegion(event) {
  event.preventDefault();
  setRegionsMessage("", "");
  const editingId = $("region_editing_id").value;
  const payload = regionPayloadFromForm();
  if (!payload.id || !payload.name || !payload.country_codes) {
    setRegionsMessage("error", "请填写地区 ID、名称和国家代码");
    return;
  }

  const submitBtn = $("regions_submit_btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "保存中...";
  try {
    const response = await fetch(editingId ? `./api/regions/${encodeURIComponent(editingId)}` : "./api/regions", {
      method: editingId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      setRegionsMessage("error", data.error || "保存地区失败");
      return;
    }
    selectedRegionId = data.region && data.region.id ? data.region.id : selectedRegionId;
    await loadRegions();
    resetRegionForm();
    setRegionsMessage("success", "地区已保存");
    await load();
  } catch (e) {
    setRegionsMessage("error", "连接服务失败，请稍后重试");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = $("region_editing_id").value ? "更新地区" : "保存地区";
  }
}

async function deleteRegion(id) {
  if (!confirm("确定删除这个地区配置吗？")) return;
  try {
    const response = await fetch(`./api/regions/${encodeURIComponent(id)}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      setRegionsMessage("error", data.error || "删除地区失败");
      return;
    }
    if (selectedRegionId === id) {
      selectedRegionId = "";
    }
    resetRegionForm();
    setRegionsMessage("success", "地区已删除");
    await loadRegions();
    await load();
  } catch (e) {
    setRegionsMessage("error", "连接服务失败，请稍后重试");
  }
}

async function previewRegion(id) {
  const previewBox = $("regions_preview");
  previewBox.innerHTML = `<div class="message-box">正在预览匹配节点...</div>`;
  try {
    const response = await fetch(`./api/regions/${encodeURIComponent(id)}/preview`, { method: "POST" });
    const data = await response.json();
    if (!response.ok || !data.ok || !data.preview) {
      previewBox.innerHTML = `<div class="message-box error">${esc(data.error || "预览失败")}</div>`;
      return;
    }
    const preview = data.preview;
    const sampleIds = Array.isArray(preview.matched_node_ids) ? preview.matched_node_ids.slice(0, 8).join(", ") : "";
    previewBox.innerHTML = `
      <div class="message-box success">
        匹配 ${esc(preview.matched_nodes)} / ${esc(preview.total_nodes)} 个节点
        ${sampleIds ? `<div class="mono" style="margin-top: 6px; white-space: normal;">${esc(sampleIds)}</div>` : ""}
      </div>
    `;
  } catch (e) {
    previewBox.innerHTML = `<div class="message-box error">连接服务失败，请稍后重试</div>`;
  }
}

async function checkRegionQuality(id) {
  if (!id || checkingRegionIds.has(id)) return;
  const previewBox = $("regions_preview");
  checkingRegionIds.add(id);
  renderRegionsList();
  if (previewBox) {
    previewBox.innerHTML = `<div class="message-box">Checking region nodes, up to 20 at a time...</div>`;
  }
  try {
    const response = await fetch("./api/quality/check-region", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region_id: id, limit: 20 })
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      if (previewBox) {
        previewBox.innerHTML = `<div class="message-box error">${esc(data.error || "Region quality check failed")}</div>`;
      }
      return;
    }
    applyRegionQualityResult(data);
    stableSortNodes();
    render();
    if (previewBox) {
      previewBox.innerHTML = `
        <div class="message-box success">
          Checked ${esc(data.tested_count || 0)} / ${esc(data.total_matches || 0)} matching nodes.
        </div>
      `;
    }
    await load();
  } catch (e) {
    if (previewBox) {
      previewBox.innerHTML = `<div class="message-box error">Region quality check failed. Please try again later.</div>`;
    }
  } finally {
    checkingRegionIds.delete(id);
    renderRegionsList();
  }
}

async function selectRegionFromModal(id) {
  selectedRegionId = id;
  updateRegionFilter();
  currentPage = 1;
  await load();
}

async function openRegionsModal() {
  $("regions_modal").style.display = "flex";
  const dropdown = $("admin_dropdown");
  if (dropdown) dropdown.style.display = "none";
  setRegionsMessage("", "");
  await loadRegions();
}

function closeRegionsModal() {
  $("regions_modal").style.display = "none";
}

// Admin dropdown toggle & GitHub dropdown toggle
