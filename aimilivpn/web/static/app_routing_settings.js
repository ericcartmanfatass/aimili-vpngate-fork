function selectOptionCard(groupName, value) {
  if (groupName === 'routing_mode') {
    const input = $("net_routing_mode");
    if (input) input.value = value;
    
    const cards = document.querySelectorAll("#routing_mode_group .option-card");
    cards.forEach(card => {
      if (card.getAttribute("data-value") === value) {
        card.classList.add("active");
      } else {
        card.classList.remove("active");
      }
    });
    
    handleRoutingModeChange(value);
  } else if (groupName === 'routing_ip_type') {
    const input = $("net_routing_ip_type");
    if (input) input.value = value;
    
    const cards = document.querySelectorAll("#routing_ip_type_group .option-card");
    cards.forEach(card => {
      if (card.getAttribute("data-value") === value) {
        card.classList.add("active");
      } else {
        card.classList.remove("active");
      }
    });
  }
}

function setRoutingMode(value) {
  selectOptionCard('routing_mode', value);
}

function setRoutingIpType(value) {
  selectOptionCard('routing_ip_type', value);
}

function handleRoutingModeChange(mode) {
  const countryGroup = $("net_force_country_group");
  const warningDiv = $("net_routing_warning");
  
  if (mode === "fixed_region") {
    countryGroup.style.display = "block";
    warningDiv.style.color = "var(--warning)";
    warningDiv.style.background = "rgba(245, 158, 11, 0.1)";
    warningDiv.style.border = "1px solid rgba(245, 158, 11, 0.2)";
    warningDiv.innerHTML = `⚠️ <strong>固定地区</strong>：限制仅连接选定国家的节点，且后台仅并发测速该国家的节点。如果该国的所有可用节点都失效，会造成代理中断且<strong>绝不自动切换到其他国家</strong>的节点。`;
  } else if (mode === "favorites") {
    countryGroup.style.display = "none";
    warningDiv.style.color = "var(--warning)";
    warningDiv.style.background = "rgba(245, 158, 11, 0.1)";
    warningDiv.style.border = "1px solid rgba(245, 158, 11, 0.2)";
    warningDiv.innerHTML = `⚠️ <strong>仅用收藏</strong>：只连接和切换您收藏的节点。如果所有收藏的节点均失效，系统不会自动切换到未收藏的节点。请确保收藏列表中有足够多且可用的节点。`;
  } else if (mode === "fixed_ip") {
    countryGroup.style.display = "none";
    warningDiv.style.color = "var(--warning)";
    warningDiv.style.background = "rgba(245, 158, 11, 0.1)";
    warningDiv.style.border = "1px solid rgba(245, 158, 11, 0.2)";
    warningDiv.innerHTML = `⚠️ <strong>固定IP</strong>：锁定当前连接的节点。不管该节点是否失效，系统都绝不自动切换至其他IP；如果节点由于网络故障失效，会造成代理中断（但如果OpenVPN连接意外退出，脚本将尝试为您在后台重新拉起连接同一IP）。<br><strong>提示</strong>：您可以在主页 of 节点列表中直接点击“连接”按钮来选择并锁定不同的IP节点。`;
  } else {
    countryGroup.style.display = "none";
    warningDiv.style.color = "var(--text-secondary)";
    warningDiv.style.background = "rgba(255, 255, 255, 0.02)";
    warningDiv.style.border = "1px solid rgba(255, 255, 255, 0.05)";
    warningDiv.innerHTML = `ℹ️ <strong>自动配置</strong>：全自动测试并选择最佳IP。在使用过程中，如果当前连接节点没有失效，将不再更换IP；如果当前节点失效，系统将立刻秒级自动漂移到其他最快的可用节点。`;
  }
}

function populateRoutingCountries() {
  const select = $("net_force_country");
  if (!select) return;
  const countMap = {};
  nodes.forEach(n => {
    const c = translateCountry(n.country);
    if (c) {
      countMap[c] = (countMap[c] || 0) + 1;
    }
  });
  
  const countries = Object.keys(countMap).sort();
  let html = '<option value="">请选择要锁定的国家...</option>';
  countries.forEach(c => {
    html += `<option value="${esc(c)}">${esc(c)} (${countMap[c]}个节点)</option>`;
  });
  select.innerHTML = html;
  
  if (state) {
    select.value = state.force_country ? translateCountry(state.force_country) : "";
  }
}

function populateRoutingTargets() {
  const select = $("net_force_country");
  if (!select) return;
  const countMap = {};
  nodes.forEach(n => {
    const c = translateCountry(n.country);
    if (c) {
      countMap[c] = (countMap[c] || 0) + 1;
    }
  });

  const countries = Object.keys(countMap).sort();
  let html = '<option value="">请选择要锁定的地区或国家...</option>';
  if (regions.length) {
    html += '<optgroup label="自定义地区">';
    regions.forEach(region => {
      const codes = Array.isArray(region.country_codes) ? region.country_codes.join(",") : "";
      html += `<option value="region:${esc(region.id)}">${esc(region.name)} (${esc(codes)})</option>`;
    });
    html += '</optgroup>';
  }
  html += '<optgroup label="国家地区">';
  countries.forEach(c => {
    html += `<option value="country:${esc(c)}">${esc(c)} (${countMap[c]}个节点)</option>`;
  });
  html += '</optgroup>';
  select.innerHTML = html;

  const target = state && state.force_country ? String(state.force_country) : "";
  if (target.startsWith("region:") || target.startsWith("country:")) {
    select.value = target;
  } else if (target) {
    select.value = regions.some(region => region.id === target)
      ? `region:${target}`
      : `country:${translateCountry(target)}`;
  } else {
    select.value = "";
  }
}
