function getActiveNodeForRender() {
  const activeNodeId = state.active_openvpn_node_id;
  return nodes.find(node => node && (node.active || node.id === activeNodeId));
}

function statusElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

function appendMeta(details, label, value, className = "") {
  const item = statusElement("span", "", `${label}: `);
  const strong = statusElement("strong", className, value || "-");
  item.append(strong);
  details.append(item);
}

function renderActiveNodeCard(activeNode) {
  const container = $("active_node_card");
  const card = statusElement("div", "active-card");
  const info = statusElement("div", "active-card-info");
  const icon = statusElement("div", "stat-icon-wrapper");
  const details = statusElement("div", "active-card-details");
  icon.setAttribute("aria-hidden", "true");
  info.append(icon, details);
  card.append(info);

  if (state.is_connecting && !activeNode) {
    card.classList.add("active-card-connecting");
    icon.textContent = "↻";
    const title = statusElement("div", "active-card-title");
    const badge = statusElement("span", "badge", "正在连接");
    const pulse = statusElement("span", "badge-pulse");
    badge.prepend(pulse);
    title.append(badge, statusElement("strong", "", state.active_node_latency || "正在连接..."));
    details.append(title, statusElement("div", "active-card-meta", state.last_check_message || "正在建立 VPN 加密通道，请稍候..."));
  } else if (activeNode) {
    icon.textContent = "⚡";
    const title = statusElement("div", "active-card-title");
    const badge = statusElement("span", "badge available", "已连接");
    badge.prepend(statusElement("span", "badge-pulse"));
    title.append(badge, statusElement("strong", "", `${translateCountry(activeNode.country)} 节点`));
    const address = statusElement(
      "div",
      "active-card-value mono",
      `${activeNode.ip || activeNode.remote_host || "-"}:${activeNode.remote_port || ""}`,
    );
    const meta = statusElement("div", "active-card-meta");
    appendMeta(meta, "物理位置", activeNode.location || translateCountry(activeNode.country));
    appendMeta(meta, "延时", activeNode.latency_ms ? `${activeNode.latency_ms} ms` : "-", getLatencyClass(activeNode.latency_ms));
    appendMeta(meta, "运营主体", activeNode.owner || activeNode.as_name || "-");
    appendMeta(meta, "IP 类型", translateIpType(activeNode.ip_type));
    details.append(title, address, meta);

    const disconnect = statusElement("button", "btn-danger", "断开连接");
    disconnect.type = "button";
    disconnect.dataset.action = "disconnect-node";
    card.append(disconnect);
  } else {
    card.classList.add("active-card-empty");
    icon.textContent = "○";
    const title = statusElement("div", "active-card-title");
    title.append(statusElement("span", "badge unavailable", "未连接"));
    title.append(document.createTextNode(" 当前未连接 VPN 节点"));
    details.append(title, statusElement("div", "active-card-meta", "请从下方列表选择可用节点并点击“切换”。"));
  }

  container.replaceChildren(card);
}

function renderSummaryStatus(activeNode) {
  if ($("total")) $("total").textContent = String(nodes.length);
  if ($("target")) $("target").textContent = String(state.target_valid_nodes || 3);
  if ($("active")) $("active").textContent = activeNode ? "1" : "0";

  const status = $("status");
  if (!status) return;
  const localProxy = state.local_proxy || `http://127.0.0.1:${state.proxy_port || 7928}`;
  const badge = statusElement(
    "span",
    activeNode ? "badge available" : "badge unavailable",
    activeNode ? `${translateCountry(activeNode.country)} (${activeNode.id || "-"})` : "无",
  );
  const statusMessage = state.last_check_message || "";
  status.replaceChildren(
    statusElement("span", "status-dot"),
    document.createTextNode(`HTTP 代理本地接口：${localProxy} | 活动节点：`),
    badge,
    document.createTextNode(` | 状态：${statusMessage}`),
  );
}

function setProxyDetail(container, text, className = "") {
  container.replaceChildren(statusElement("span", className, text));
}

function renderProxyStatusCard() {
  const badge = $("proxy_status_badge");
  const ipValue = $("proxy_ip_val");
  const latencyValue = $("proxy_latency_val");
  const button = $("btn_test_proxy");

  if (state.is_connecting) {
    badge.className = "badge";
    badge.replaceChildren(statusElement("span", "badge-pulse"), document.createTextNode("正在连接"));
    ipValue.textContent = state.active_node_latency || "正在连接...";
    setProxyDetail(latencyValue, state.last_check_message || "正在建立 VPN 加密通道，请稍候...");
    button.disabled = true;
    return;
  }

  button.disabled = false;
  if (state.proxy_ok === true) {
    badge.className = "badge available";
    badge.textContent = "可用";
    ipValue.textContent = state.proxy_ip || "-";
    setProxyDetail(latencyValue, `${state.proxy_latency_ms || 0} ms`, `latency-val ${getLatencyClass(state.proxy_latency_ms)}`);
  } else if (state.proxy_ok === false) {
    badge.className = "badge unavailable";
    badge.textContent = "不可用";
    ipValue.textContent = "-";
    setProxyDetail(latencyValue, state.proxy_error || "连接失败", "latency-val latency-poor");
  } else {
    badge.className = "badge not_checked";
    badge.textContent = "未检测";
    ipValue.textContent = "-";
    setProxyDetail(latencyValue, state.last_check_message || "");
  }
}
