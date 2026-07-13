// Hook up page buttons events
$("btn_first_page").addEventListener("click", async () => { currentPage = 1; await load().catch(() => {}); });
$("btn_prev_page").addEventListener("click", async () => {
  if (currentPage > 1) {
    currentPage--;
    await load().catch(() => {});
  }
});
$("btn_next_page").addEventListener("click", async () => {
  const totalPages = Math.ceil(Number(nodePagination.total || 0) / pageSize) || 1;
  if (currentPage < totalPages) {
    currentPage++;
    await load().catch(() => {});
  }
});
$("btn_last_page").addEventListener("click", async () => {
  currentPage = Math.ceil(Number(nodePagination.total || 0) / pageSize) || 1;
  await load().catch(() => {});
});

async function toggleFavorite(id, event) {
  if (event) event.stopPropagation();
  try {
    const response = await fetch("./api/toggle_favorite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    const result = await response.json();
    if (result.ok) {
      state.favorite_node_ids = Array.isArray(result.favorite_node_ids) ? result.favorite_node_ids : [];
      render();
    }
  } catch (e) {
    console.error("切换收藏失败", e);
  }
}

let pollInterval = null;

async function waitForOperation(operationId, timeoutMs = 30000) {
  if (!operationId) return null;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const response = await fetch(`./api/v1/operations/${encodeURIComponent(operationId)}`);
    const payload = await response.json();
    const operation = payload.operation || payload;
    if (["succeeded", "failed"].includes(operation.status)) return operation;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error("operation_timeout");
}

function startConnectionPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const resp = await fetch(nodesApiUrl());
      const data = await resp.json();
      nodes = Array.isArray(data.nodes) ? data.nodes : [];
      state = data.state || {};
      nodePagination = data.pagination || nodePagination;
      stableSortNodes();
      updateCountryFilter();
      render();
      
      if (!state.is_connecting) {
        clearInterval(pollInterval);
        pollInterval = null;
        try {
          await fetch("./api/v1/proxy-checks", { method: "POST" });
        } catch(pe){}
        load().catch(() => {});
      }
    } catch(pe) {
      clearInterval(pollInterval);
      pollInterval = null;
      load().catch(() => {});
    }
  }, 1000);
}

async function connectNode(id){
  state.is_connecting = true;
  state.active_openvpn_node_id = id;
  state.active_node_latency = "正在连接";
  state.last_check_message = "正在发送连接请求...";
  render();
  
  startConnectionPolling();
  
  try {
    const r = await fetch("./api/v1/operations/connect",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id})
    });
    const result = await r.json();
    if (!result.ok) {
      alert("连接失败: " + (result.error || "未知错误"));
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
      state.is_connecting = false;
      render();
      return;
    }
  } catch(e) {
    alert("连接请求错误");
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
    state.is_connecting = false;
    render();
  }
}

async function disconnectNode(){
  if (!confirm("确定要断开当前的 VPN 连接吗？")) return;
  try {
    const response = await fetch("./api/v1/operations/disconnect", { method: "POST" });
    const result = await response.json();
    if (result.ok) {
      const operation = await waitForOperation(result.operation_id);
      if (operation && operation.status !== "succeeded") {
        throw new Error(operation.error_code || "disconnect_failed");
      }
      try {
        await fetch("./api/v1/proxy-checks", { method: "POST" });
      } catch(pe){}
      load();
    } else {
      alert("断开连接失败: " + (result.error || "未知错误"));
    }
  } catch (e) {
    alert("请求断开连接失败");
  }
}

$("country_filter").addEventListener("change",async()=>{ currentPage = 1; await load().catch(() => {}); });
$("ip_type_filter").addEventListener("change",async()=>{ currentPage = 1; await load().catch(() => {}); });
$("status_filter").addEventListener("change",async()=>{ currentPage = 1; await load().catch(() => {}); });
$("region_filter").addEventListener("change",async()=>{ selectedRegionId = $("region_filter").value; currentPage = 1; await load(); });

$("select_all_nodes").addEventListener("change", event => {
  for (const node of currentPageNodes) {
    if (event.target.checked) selectedNodeIds.add(node.id);
    else selectedNodeIds.delete(node.id);
  }
  render();
});

document.addEventListener("change", event => {
  const checkbox = event.target.closest("input[data-node-select]");
  if (!checkbox) return;
  const nodeId = checkbox.dataset.nodeId || "";
  if (checkbox.checked) selectedNodeIds.add(nodeId);
  else selectedNodeIds.delete(nodeId);
  $("btn_test_selected").disabled = selectedNodeIds.size === 0;
  $("selected_node_count").textContent = String(selectedNodeIds.size);
});

$("btn_test_selected").addEventListener("click", async event => {
  const ids = [...selectedNodeIds];
  if (!ids.length) return;
  if (ids.length > 100) {
    alert("一次最多检测 100 个节点。");
    return;
  }
  const button = event.currentTarget;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("./api/v1/quality-checks/nodes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "批量检测失败");
    await waitForOperation(result.operation_id);
    selectedNodeIds.clear();
    await load();
  } catch (error) {
    alert(error.message || "批量检测失败");
  } finally {
    button.removeAttribute("aria-busy");
    button.disabled = selectedNodeIds.size === 0;
  }
});

$("refresh").addEventListener("click",async()=>{
  $("refresh").disabled=true; 
  $("refresh").textContent="正在后台更新..."; 
  try{
    const response = await fetch("./api/v1/operations/refresh-nodes",{method:"POST"});
    const result = await response.json();
    if (result.ok) await waitForOperation(result.operation_id);
    await load();
  }
  catch(e){}
  setTimeout(()=>{
    $("refresh").disabled=false; 
    $("refresh").textContent="更新节点";
  }, 3000);
});
$("btn_test_proxy").addEventListener("click", async () => {
  const btn = $("btn_test_proxy");
  const badge = $("proxy_status_badge");
  const ipVal = $("proxy_ip_val");
  const latVal = $("proxy_latency_val");
  
  btn.disabled = true;
  btn.innerHTML = `<span class="badge-pulse"></span>测试中...`;
  badge.className = "badge not_checked";
  badge.textContent = "检测中...";
  ipVal.textContent = "-";
  latVal.textContent = "";
  
  try {
    const response = await fetch("./api/v1/proxy-checks", { method: "POST" });
    const result = await response.json();
    if (result.ok) {
      badge.className = "badge available";
      badge.textContent = "可用";
      ipVal.textContent = result.ip || "-";
      
      const latency = Number(result.latency_ms);
      const latencyClass = getLatencyClass(Number.isFinite(latency) ? latency : 0);
      latVal.innerHTML = `<span class="latency-val ${latencyClass}" style="margin-left:8px;">${Number.isFinite(latency) ? latency : 0} ms</span>`;
    } else {
      badge.className = "badge unavailable";
      badge.textContent = "不可用";
      ipVal.textContent = "-";
      latVal.innerHTML = `<span class="latency-val latency-poor" style="margin-left:8px; font-size:11px;" title="${esc(result.error)}">连接失败</span>`;
    }
  } catch (e) {
    badge.className = "badge unavailable";
    badge.textContent = "网络错误";
    ipVal.textContent = "-";
    latVal.innerHTML = `<span class="latency-val latency-poor" style="margin-left:8px; font-size:11px;">请求出错</span>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" style="width:16px; height:16px;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> 测试代理`;
  }
});
