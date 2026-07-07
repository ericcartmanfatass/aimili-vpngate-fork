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
