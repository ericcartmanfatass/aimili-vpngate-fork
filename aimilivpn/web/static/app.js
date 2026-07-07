let nodes=[], state={}, regions=[], testingNodeIds = new Set(), checkingRegionIds = new Set();
let currentPage = 1;
const pageSize = 99999;
let currentPageNodes = [];
let selectedRegionId = "";
let currentQualityModalNodeId = "";

function updateCountryFilter() {
  const select = $("country_filter");
  const selectedValue = select.value;
  const countries = Array.from(new Set(nodes.map(n => n ? translateCountry(n.country) : "").filter(Boolean))).sort();
  
  const currentOptions = Array.from(select.options).map(o => o.value).filter(Boolean);
  if (JSON.stringify(countries) === JSON.stringify(currentOptions)) {
    return;
  }
  
  select.innerHTML = '<option value="">所有国家</option>' + 
    countries.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  
  if (countries.includes(selectedValue)) {
    select.value = selectedValue;
  } else {
    select.value = "";
  }
}

function nodesApiUrl() {
  const query = selectedRegionId ? `?region=${encodeURIComponent(selectedRegionId)}` : "";
  return `./api/nodes${query}`;
}

function updateRegionFilter() {
  const select = $("region_filter");
  if (!select) return;
  const current = selectedRegionId || select.value;
  select.innerHTML = '<option value="">所有地区</option>' +
    regions.map(region => `<option value="${esc(region.id)}">${esc(region.name)} (${esc((region.country_codes || []).join(","))})</option>`).join("");
  if (regions.some(region => region.id === current)) {
    select.value = current;
    selectedRegionId = current;
  } else {
    select.value = "";
    selectedRegionId = "";
  }
}

async function loadRegions() {
  try {
    const response = await fetch("./api/regions");
    const data = await response.json();
    regions = Array.isArray(data.regions) ? data.regions : [];
  } catch (e) {
    regions = [];
  }
  updateRegionFilter();
  renderRegionsList();
}

function getFilteredNodes() {
  const selectedCountry = $("country_filter").value;
  const selectedIpType = $("ip_type_filter").value;
  const selectedStatus = $("status_filter").value;
  return nodes.filter(n => {
    if (!n) return false;
    if (selectedCountry && translateCountry(n.country) !== selectedCountry) {
      return false;
    }
    if (selectedIpType) {
      if (selectedIpType === "residential" && !["residential", "mobile"].includes(n.ip_type)) {
        return false;
      }
      if (selectedIpType === "hosting" && n.ip_type !== "hosting") {
        return false;
      }
    }
    if (selectedStatus === "available" && n.probe_status !== "available" && !n.active) {
      return false;
    }
    if (selectedStatus === "unavailable" && (n.probe_status !== "unavailable" || n.active)) {
      return false;
    }
    const favoriteIds = Array.isArray(state.favorite_node_ids) ? state.favorite_node_ids : [];
    if (showFavoritesOnly && !favoriteIds.includes(n.id)) {
      return false;
    }
    return true;
  });
}

function stableSortNodes() {
  nodes.sort((a, b) => {
    if (!a || !b) return 0;
    const aScore = a.score || 0;
    const bScore = b.score || 0;
    if (bScore !== aScore) {
      return bScore - aScore;
    }
    const aId = a.id || "";
    const bId = b.id || "";
    return aId.localeCompare(bId);
  });
}

// Hook up page buttons events
$("btn_first_page").onclick = () => { currentPage = 1; render(); };
$("btn_prev_page").onclick = () => { if (currentPage > 1) { currentPage--; render(); } };
$("btn_next_page").onclick = () => {
  const shown = getFilteredNodes();
  const totalPages = Math.ceil(shown.length / pageSize) || 1;
  if (currentPage < totalPages) { currentPage++; render(); }
};
$("btn_last_page").onclick = () => {
  const shown = getFilteredNodes();
  const totalPages = Math.ceil(shown.length / pageSize) || 1;
  currentPage = totalPages;
  render();
};

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

function startConnectionPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const resp = await fetch(nodesApiUrl());
      const data = await resp.json();
      nodes = Array.isArray(data.nodes) ? data.nodes : [];
      state = data.state || {};
      stableSortNodes();
      updateCountryFilter();
      render();
      
      if (!state.is_connecting) {
        clearInterval(pollInterval);
        pollInterval = null;
        try {
          await fetch("./api/test_proxy", { method: "POST" });
        } catch(pe){}
        load();
      }
    } catch(pe) {
      clearInterval(pollInterval);
      pollInterval = null;
      load();
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
    const r = await fetch("./api/connect",{
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
    const response = await fetch("./api/disconnect", { method: "POST" });
    const result = await response.json();
    if (result.ok) {
      try {
        await fetch("./api/test_proxy", { method: "POST" });
      } catch(pe){}
      load();
    } else {
      alert("断开连接失败: " + (result.error || "未知错误"));
    }
  } catch (e) {
    alert("请求断开连接失败");
  }
}





async function load(){
  await loadRegions();
  const r=await fetch(nodesApiUrl()); 
  const d=await r.json(); 
  nodes=Array.isArray(d.nodes) ? d.nodes : []; 
  state=d.state||{}; 
  
  stableSortNodes();
  updateCountryFilter();
  render();

  if (state.is_connecting) {
    startConnectionPolling();
  }
}
$("country_filter").onchange=()=>{ currentPage = 1; render(); };
$("ip_type_filter").onchange=()=>{ currentPage = 1; render(); };
$("status_filter").onchange=()=>{ currentPage = 1; render(); };
$("region_filter").onchange=async()=>{ selectedRegionId = $("region_filter").value; currentPage = 1; await load(); };

$("refresh").onclick=async()=>{ 
  $("refresh").disabled=true; 
  $("refresh").textContent="正在后台更新..."; 
  try{await fetch("./api/refresh_nodes",{method:"POST"}); await load();} 
  catch(e){}
  setTimeout(()=>{
    $("refresh").disabled=false; 
    $("refresh").textContent="更新节点";
  }, 3000);
};
$("btn_test_proxy").onclick = async () => {
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
    const response = await fetch("./api/test_proxy", { method: "POST" });
    const result = await response.json();
    if (result.ok) {
      badge.className = "badge available";
      badge.textContent = "可用";
      ipVal.textContent = result.ip || "-";
      
      const latencyClass = getLatencyClass(result.latency_ms);
      latVal.innerHTML = `<span class="latency-val ${latencyClass}" style="margin-left:8px;">${result.latency_ms} ms</span>`;
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
};

// 页面加载时自动初始化数据
load();

// 每 10 秒在前台空闲时自动更新节点与状态，无需手动刷新页面
setInterval(async () => {
  if (typeof state !== "undefined" && !state.is_connecting && (!testingNodeIds || !testingNodeIds.size) && document.visibilityState === "visible") {
    try {
      const r = await fetch(nodesApiUrl());
      const d = await r.json();
      nodes = d.nodes || [];
      state = d.state || {};
      stableSortNodes();
      updateCountryFilter();
      render();
    } catch(e) {}
  }
}, 10000);
