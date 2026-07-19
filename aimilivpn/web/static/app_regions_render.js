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
          <button type="button" class="test-btn" data-action="check-region" data-region-id="${esc(region.id)}" ${isChecking ? "disabled" : ""}>${isChecking ? "检测中……" : "检测"}</button>
          <button type="button" class="test-btn" data-action="edit-region" data-region-id="${esc(region.id)}">编辑</button>
          <button type="button" class="test-btn" data-action="preview-region" data-region-id="${esc(region.id)}">预览</button>
          <button type="button" class="connect-btn" data-action="select-region" data-region-id="${esc(region.id)}">筛选</button>
          <button type="button" class="test-btn" data-action="delete-region" data-region-id="${esc(region.id)}" style="color: var(--danger); border-color: rgba(244, 63, 94, 0.35);">删除</button>
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
