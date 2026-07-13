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
    const exclusions = preview.exclusion_reasons || {};
    const notTested = Number(exclusions.quality_not_tested || 0) + Number(exclusions.risk_not_tested || 0);
    previewBox.innerHTML = `
      <div class="message-box success">
        匹配 ${esc(preview.matched_nodes)} / ${esc(preview.total_nodes)} 个节点
        ${sampleIds ? `<div class="mono" style="margin-top: 6px; white-space: normal;">${esc(sampleIds)}</div>` : ""}
        ${notTested ? `<div class="muted" style="margin-top: 6px;">${esc(notTested)} 个节点因尚未完成所需质量/风险检测而被排除</div>` : ""}
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
