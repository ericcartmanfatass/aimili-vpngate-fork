let nodes = [];
let state = {};
let regions = [];
let testingNodeIds = new Set();
let checkingRegionIds = new Set();
let selectedNodeIds = new Set();
let currentPage = 1;
const pageSize = 50;
let nodePagination = { limit: pageSize, offset: 0, returned: 0, total: 0 };
let currentPageNodes = [];
let selectedRegionId = "";
let currentQualityModalNodeId = "";
const knownCountries = new Map();

function updateCountryFilter() {
  const select = $("country_filter");
  const selectedValue = select.value;
  for (const node of nodes) {
    if (!node) continue;
    const code = String(node.country_short || "").toUpperCase();
    if (code) knownCountries.set(code, translateCountry(node.country || code));
  }
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "所有国家";
  const options = [...knownCountries.entries()]
    .sort((left, right) => left[1].localeCompare(right[1]))
    .map(([code, name]) => {
      const option = document.createElement("option");
      option.value = code;
      option.textContent = `${name} (${code})`;
      return option;
    });
  select.replaceChildren(all, ...options);
  select.value = knownCountries.has(selectedValue) ? selectedValue : "";
}

function nodesApiUrl() {
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String((currentPage - 1) * pageSize),
    sort: "quality",
    order: "desc",
  });
  const country = $("country_filter").value;
  const status = $("status_filter").value;
  const ipType = $("ip_type_filter").value;
  if (selectedRegionId) params.set("region", selectedRegionId);
  if (country) params.set("country", country);
  if (status && status !== "all") params.set("status", status);
  if (ipType) params.set("ip_type", ipType);
  return `./api/v1/nodes?${params.toString()}`;
}

function updateRegionFilter() {
  const select = $("region_filter");
  if (!select) return;
  const current = selectedRegionId || select.value;
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "所有地区";
  const options = regions.map(region => {
    const option = document.createElement("option");
    option.value = String(region.id || "");
    option.textContent = `${region.name || "-"} (${(region.country_codes || []).join(",")})`;
    return option;
  });
  select.replaceChildren(all, ...options);
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
    const response = await fetch("./api/v1/regions?limit=100&sort=name&order=asc");
    const data = await response.json();
    regions = response.ok && Array.isArray(data.regions) ? data.regions : [];
  } catch (error) {
    regions = [];
  }
  updateRegionFilter();
  renderRegionsList();
}

function getFilteredNodes() {
  const favoriteIds = Array.isArray(state.favorite_node_ids) ? state.favorite_node_ids : [];
  return nodes.filter(node => node && (!showFavoritesOnly || favoriteIds.includes(node.id)));
}

function stableSortNodes() {
  nodes.sort((left, right) => {
    if (!left || !right) return 0;
    const scoreDifference = Number(right.quality_score || right.score || 0) - Number(left.quality_score || left.score || 0);
    return scoreDifference || String(left.id || "").localeCompare(String(right.id || ""));
  });
}

function setDashboardMessage(message, kind = "") {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 8;
  cell.className = `table-state ${kind}`.trim();
  cell.textContent = message;
  row.append(cell);
  $("rows").replaceChildren(row);
}

async function load() {
  setDashboardMessage("正在加载节点与状态...", "loading");
  try {
    await loadRegions();
    const response = await fetch(nodesApiUrl());
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "节点加载失败");
    nodes = Array.isArray(data.nodes) ? data.nodes : [];
    state = data.state || {};
    nodePagination = data.pagination || { limit: pageSize, offset: 0, returned: nodes.length, total: nodes.length };
    stableSortNodes();
    updateCountryFilter();
    render();
    if (state.is_connecting) startConnectionPolling();
  } catch (error) {
    setDashboardMessage(error.message || "节点加载失败，请稍后重试。", "error");
    throw error;
  }
}
