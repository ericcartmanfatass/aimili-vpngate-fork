function renderNodeRows(activeNode, shown) {
  const total = showFavoritesOnly ? shown.length : Number(nodePagination.total || shown.length);
  const offset = showFavoritesOnly ? 0 : Number(nodePagination.offset || 0);
  const limit = Number(nodePagination.limit || pageSize);
  const totalPages = Math.ceil(total / limit) || 1;
  if (currentPage > totalPages) currentPage = totalPages;
  currentPageNodes = shown;

  if (!shown.length) {
    setDashboardMessage("未找到符合过滤条件的备选节点。", "empty");
  } else {
    const rows = shown.map(node => {
      const isActive = Boolean(activeNode && node.id === activeNode.id);
      const allowedStatuses = ["available", "unavailable", "not_checked"];
      const badgeClass = isActive ? "available" : (allowedStatuses.includes(node.probe_status) ? node.probe_status : "not_checked");
      const badgeText = isActive ? '<span class="badge-pulse"></span>已连接' : esc(translateStatus(node.probe_status));
      const location = node.location || translateCountry(node.country) || "-";
      const remotePort = Number.isInteger(Number(node.remote_port)) ? Number(node.remote_port) : "";
      const isUnavailable = node.probe_status === "unavailable";
      const isFavorite = Array.isArray(state.favorite_node_ids) && state.favorite_node_ids.includes(node.id);
      const selected = selectedNodeIds.has(node.id) ? "checked" : "";
      const favoriteButton = `<button class="test-btn" data-action="toggle-favorite" data-node-id="${esc(node.id)}" style="color: ${isFavorite ? "var(--warning)" : "var(--text-secondary)"}; padding: 0 8px; height: 30px;">${isFavorite ? "★ 已收藏" : "☆ 收藏"}</button>`;
      const connectButton = isActive
        ? '<button class="connect-btn" disabled>已连接</button>'
        : `<button class="connect-btn" data-action="connect-node" data-node-id="${esc(node.id)}" ${(isUnavailable || state.is_connecting) ? "disabled" : ""}>切换</button>`;
      return `<tr class="${isActive ? "active-row" : ""}">
        <td><input type="checkbox" data-node-select data-node-id="${esc(node.id)}" ${selected} aria-label="选择节点 ${esc(node.id)}"></td>
        <td><span class="badge ${badgeClass}">${badgeText}</span></td>
        <td class="mono" title="${esc(node.ip || node.remote_host)}:${remotePort}">${esc(node.ip || node.remote_host)}:${remotePort}</td>
        <td title="${esc(location)}">${esc(location)}</td>
        <td title="${esc(node.owner || node.as_name || "-")}">${esc(node.owner || node.as_name || "-")}</td>
        <td title="${esc(translateIpType(node.ip_type))}">${esc(translateIpType(node.ip_type))}</td>
        <td>${qualityBadgeHtml(node)}</td>
        <td><div class="table-actions">${favoriteButton}${connectButton}</div></td>
      </tr>`;
    });
    $("rows").innerHTML = rows.join("");
  }

  const start = total ? offset + 1 : 0;
  const end = Math.min(offset + shown.length, total);
  $("page_start").textContent = String(start);
  $("page_end").textContent = String(end);
  $("filtered_count").textContent = String(total);
  $("current_page_val").textContent = String(currentPage);
  $("total_pages_val").textContent = String(totalPages);
  $("btn_first_page").disabled = currentPage === 1;
  $("btn_prev_page").disabled = currentPage === 1;
  $("btn_next_page").disabled = currentPage >= totalPages;
  $("btn_last_page").disabled = currentPage >= totalPages;
  $("btn_test_selected").disabled = selectedNodeIds.size === 0;
  $("selected_node_count").textContent = String(selectedNodeIds.size);
  $("select_all_nodes").checked = shown.length > 0 && shown.every(node => selectedNodeIds.has(node.id));
}
