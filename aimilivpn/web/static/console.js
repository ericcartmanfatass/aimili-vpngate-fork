let instanceList = [];
let instanceCatalog = [];
let currentInstanceId = null;
let globalSettings = {};
let globalTask = {};
let globalNodes = [];
let overviewInstanceFilter = "all";
const globalNodePreset = { availability: "", riskLevel: "", minRisk: "", maxRisk: "" };

function el(id) {
  return document.getElementById(id);
}

function dom(tag, className = "", text = undefined) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function accessible(control, label) {
  control.ariaLabel = label;
  if (!control.title) control.title = label;
  return control;
}

function actionButton(label, action, data = {}, className = "") {
  const button = dom("button", className, label);
  button.type = "button";
  button.dataset.consoleAction = action;
  for (const [name, value] of Object.entries(data)) button.dataset[name] = String(value);
  return button;
}

function ensureGlobalTabs() {
  const tabs = typeof document.querySelector === "function" ? document.querySelector(".tabs") : null;
  if (!tabs || el("tabGlobalNodes")) return;
  const anchor = el("instanceTabs");
  const nodesTab = actionButton("全局节点", "global-nodes", { resetFilters: "true" }, "tab");
  nodesTab.id = "tabGlobalNodes";
  const tasksTab = actionButton("任务与质量", "global-tasks", {}, "tab");
  tasksTab.id = "tabGlobalTasks";
  const logsTab = actionButton("日志与安全", "global-logs", {}, "tab");
  logsTab.id = "tabGlobalLogs";
  tabs.insertBefore(nodesTab, anchor || null);
  tabs.insertBefore(tasksTab, anchor || null);
  tabs.insertBefore(logsTab, anchor || null);
}

function activateTab(id) {
  document.querySelectorAll(".tab").forEach(tab => tab.classList.remove("active"));
  el(id)?.classList.add("active");
}

async function api(path, options = {}) {
  const response = await fetch(`./api/${path}`, options);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (error) {
    throw new Error(`服务器返回格式无效（${response.status}）`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(typeof data.error === "string" ? data.error : `请求失败（${response.status}）`);
  }
  return data;
}

function setOperation(message, kind = "") {
  const status = el("operationStatus");
  status.className = `operation-status ${kind}`.trim();
  status.textContent = message;
}

function showError(message) {
  const card = dom("div", "card bad");
  card.append(dom("b", "", "操作失败"), dom("div", "", message || "未知错误"));
  el("content").prepend(card);
  setOperation(message || "操作失败", "bad");
}

function serviceStatus(instance) {
  return dom("span", instance.service_active ? "ok" : "bad", instance.service_active ? "运行中" : "已停止");
}

function resourceSummary(instance) {
  return `代理 ${instance.proxy_port || "-"} · ${instance.tun_dev || "-"} · 路由表 ${instance.policy_table || "-"}`;
}

async function load() {
  setOperation("正在加载实例和全局任务…", "loading");
  const [instancesPayload, catalogPayload, settingsPayload, taskPayload, nodesPayload] = await Promise.all([
    api("instances"),
    api("instance-catalog"),
    api("global/settings"),
    api("global/tasks"),
    api("global/nodes"),
  ]);
  instanceList = Array.isArray(instancesPayload.instances) ? instancesPayload.instances : [];
  instanceCatalog = Array.isArray(catalogPayload.catalog) ? catalogPayload.catalog : [];
  globalSettings = settingsPayload.settings || {};
  globalTask = taskPayload.task || {};
  globalNodes = Array.isArray(nodesPayload.nodes) ? nodesPayload.nodes : [];
  ensureGlobalTabs();
  renderSidebar();
  showOverview();
  setOperation("就绪", "ok");
}

function renderSidebar() {
  const container = el("instances");
  const cards = instanceList.map(instance => {
    const card = dom("div", "card");
    const heading = dom("div", "row");
    heading.append(dom("b", "", instance.country || "-"), dom("span", "pill", instance.id || "-"));
    const actions = dom("div", "toolbar compact");
    actions.append(
      actionButton("打开", "open", { instanceId: instance.id }),
      actionButton("重启", "service", { instanceId: instance.id, serviceAction: "restart" }),
    );
    card.append(heading, dom("div", "muted", resourceSummary(instance)), serviceStatus(instance), actions);
    return card;
  });
  container.replaceChildren(...cards);
  renderCatalogForm();
}

function renderCatalogForm() {
  const panel = el("instanceManager");
  const available = instanceCatalog.filter(item => !item.installed && item.creatable !== false && Number(item.node_count || 0) > 0);
  const title = dom("h3", "", "添加 VPNGate 国家/地区实例");
  const hint = dom("p", "muted", "国家/地区来自最新全局节点快照，系统资源由后端分配并校验。");
  if (!available.length) {
    panel.replaceChildren(title, hint, dom("div", "empty-state", "当前没有可添加的 VPNGate 国家/地区，请先刷新节点。"));
    return;
  }
  const select = dom("select");
  accessible(select, "选择要创建的国家或地区实例");
  select.id = "catalogCountry";
  for (const item of available) {
    const option = dom("option", "", `${item.name || item.country} (${item.country}) · ${item.node_count || 0} 个节点`);
    option.value = item.country;
    select.append(option);
  }
  const resources = dom("div", "muted");
  resources.id = "catalogResources";
  const create = actionButton("创建并启动", "create", {}, "primary");
  panel.replaceChildren(title, hint, select, resources, create);
  updateCatalogResources();
}

function updateCatalogResources() {
  const select = el("catalogCountry");
  const target = el("catalogResources");
  if (!select || !target) return;
  const item = instanceCatalog.find(entry => entry.country === select.value);
  target.textContent = item ? resourceSummary(item) : "";
}

function table(headers) {
  const tableElement = dom("table");
  const head = dom("thead");
  const row = dom("tr");
  for (const header of headers) row.append(dom("th", "", header));
  head.append(row);
  const body = dom("tbody");
  tableElement.append(head, body);
  return [tableElement, body];
}

function cell(text) {
  return dom("td", "", text === undefined || text === null || text === "" ? "-" : text);
}

function asEpoch(value) {
  if (!value) return 0;
  const number = Number(value);
  if (Number.isFinite(number)) return number > 100000000000 ? number / 1000 : number;
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed / 1000 : 0;
}

function numericRiskScore(quality) {
  const raw = quality?.risk_score;
  if (raw === undefined || raw === null || raw === "") return Number.NaN;
  const score = Number(raw);
  return Number.isFinite(score) ? score : Number.NaN;
}

function riskBucket(quality) {
  const level = String(quality?.risk_level || "").trim().toLowerCase();
  if (level) return level;
  const score = numericRiskScore(quality);
  if (!Number.isFinite(score)) return "unknown";
  if (score >= 70) return "high";
  if (score >= 40) return "medium";
  return "low";
}

function stateRoutingSummary(state = {}) {
  const labels = { auto: "自动", fixed_ip: "固定 IP", fixed_region: "固定地区", favorites: "收藏优先" };
  const routing = labels[String(state.routing_mode || "auto")] || String(state.routing_mode || "auto");
  const enabled = state.connection_enabled === false ? "已禁用" : "已启用";
  const retry = asEpoch(state.next_retry_at || state.connection_next_retry_at || state.global_next_retry_at);
  const retryText = retry ? `；下次重试 ${formatTimestamp(retry)}` : "";
  return `路由：${routing}；连接：${enabled}${retryText}`;
}

function qualityQueueErrorMessage(value) {
  const labels = {
    TimeoutError: "质量服务请求超时",
    HTTPError: "质量服务返回 HTTP 错误",
    URLError: "无法连接质量服务",
    JSONDecodeError: "质量服务返回无效数据",
    RuntimeError: "质量服务暂时不可用",
  };
  return labels[String(value || "")] || (value ? `质量检测失败（${value}）` : "-");
}

function overviewStat(label, value, action, data = {}) {
  const button = actionButton("", action, data, "stat-card");
  button.append(dom("span", "stat-label", label), dom("strong", "", value));
  return button;
}

function translateNodeStatus(value) {
  const labels = {
    active: "已连接",
    available: "可用",
    unavailable: "不可用",
    not_checked: "未检测",
    failed: "失败",
  };
  return labels[String(value || "")] || value || "未标记";
}

function showOverview(instanceFilter = overviewInstanceFilter) {
  overviewInstanceFilter = instanceFilter || "all";
  currentInstanceId = null;
  document.querySelectorAll(".tab").forEach(tab => tab.classList.remove("active"));
  el("tabOverview").classList.add("active");
  const card = dom("div", "card");
  card.append(dom("h2", "", "全局总览"));
  const connected = instanceList.filter(item => item.service_active && item.active_node).length;
  const highRisk = globalNodes.filter(node => riskBucket(node.quality_result || {}) === "high").length;
  const queueCount = Array.isArray(globalTask.quality_queue) ? globalTask.quality_queue.length : 0;
  const stats = dom("div", "stat-grid");
  stats.append(
    overviewStat("已管理实例", String(instanceList.length), "overview", { instanceFilter: "all" }),
    overviewStat("已连接实例", String(connected), "overview", { instanceFilter: "connected" }),
    overviewStat("全局节点", String(globalNodes.length), "global-nodes", { resetFilters: "true" }),
    overviewStat("高风险节点", String(highRisk), "global-nodes", { riskLevel: "high" }),
    overviewStat("质量待处理", String(queueCount), "global-tasks", { focusQueue: "true" }),
    overviewStat("任务失败计数", String(globalTask.failure_count || 0), "global-tasks"),
  );
  const metrics = globalTask.quality_metrics || {};
  const taskSummary = dom("div", "task-summary");
  taskSummary.append(
    dom("div", "muted", `VPNGate：${globalTask.status || "未执行"} · 上次成功 ${formatTimestamp(globalTask.last_success_at)} · 下次运行 ${formatTimestamp(globalTask.next_run_at)} · 最近耗时 ${Number(globalTask.duration_seconds || 0).toFixed(1)} 秒`),
    dom("div", globalTask.last_error ? "bad" : "muted", `最近失败：${globalTask.last_error || "无"}`),
    dom("div", "muted", `Scamalytics：${globalSettings.scamalytics_enabled ? "已启用" : "未启用"} · 今日请求 ${metrics.requests || 0} · 成功 ${metrics.successes || 0} · 失败 ${metrics.failures || 0} · 积压 ${queueCount}`),
  );
  card.append(stats, taskSummary, globalControlCard());
  if (!instanceList.length) {
    card.append(dom("div", "empty-state", "当前没有已管理实例。"));
    el("content").replaceChildren(card);
    return;
  }
  const [instancesTable, body] = table(["国家/地区", "服务", "代理", "TUN", "当前节点", "消息", "操作"]);
  const visibleInstances = overviewInstanceFilter === "connected"
    ? instanceList.filter(item => item.service_active && item.active_node)
    : instanceList;
  if (overviewInstanceFilter === "connected") {
    card.append(dom("div", "filter-summary", `当前筛选：已连接实例（${visibleInstances.length}）`));
  }
  for (const instance of visibleInstances) {
    const row = dom("tr");
    const statusCell = dom("td");
    statusCell.append(serviceStatus(instance));
    const actionCell = dom("td");
    actionCell.append(actionButton("管理", "open", { instanceId: instance.id }));
    row.append(
      cell(instance.country),
      statusCell,
      cell(instance.local_proxy),
      cell(instance.tun_dev),
      cell(instance.active_node && instance.active_node.ip),
      cell(`${stateRoutingSummary(instance.state)}；${instance.state?.last_check_message || "-"}`),
      actionCell,
    );
    body.append(row);
  }
  if (!visibleInstances.length) {
    const row = dom("tr"); const empty = dom("td", "empty-state", "没有符合当前筛选的实例。"); empty.colSpan = 7; row.append(empty); body.append(row);
  }
  card.append(instancesTable);
  el("content").replaceChildren(card);
}

function globalControlCard() {
  const card = dom("div", "card");
  const title = dom("div", "row");
  title.append(dom("h3", "", "全局任务"), dom("span", globalTask.status === "ok" ? "ok" : "muted", globalTask.status === "ok" ? "最近更新成功" : (globalTask.status || "未执行")));
  const details = dom("div", "muted", `节点 ${globalTask.node_count || 0} 个 · 计划时间 ${formatTimestamp(globalTask.next_run_at)} · Scamalytics ${globalSettings.scamalytics_enabled ? "已启用" : "未启用"}`);
  const toolbar = dom("div", "toolbar");
  toolbar.append(
    actionButton("查看全局节点", "global-nodes", { resetFilters: "true" }),
    actionButton("查看任务与质量", "global-tasks"),
  );
  toolbar.append(actionButton("立即更新节点", "global-refresh", {}, "primary"));
  const download = dom("a", "button");
  download.href = "./api/global/backup?type=config";
  download.download = "aimilivpn-v1.0.3-config.json";
  download.textContent = "下载配置备份";
  toolbar.append(download);
  const fullDownload = dom("a", "button");
  fullDownload.href = "./api/global/backup?type=full";
  fullDownload.download = "aimilivpn-v1.0.3-full.json";
  fullDownload.textContent = "下载完整业务备份";
  toolbar.append(fullDownload);
  const settings = dom("div", "global-settings-form");
  const schedulerEnabled = dom("input"); schedulerEnabled.type = "checkbox"; schedulerEnabled.id = "globalVpnGateEnabled"; schedulerEnabled.checked = globalSettings.vpn_gate_enabled !== false;
  const schedulerLabel = dom("label", "muted", "启用每日节点更新"); schedulerLabel.prepend(schedulerEnabled);
  const schedule = accessible(dom("input"), "VPNGate 每日更新时间"); schedule.type = "time"; schedule.id = "globalVpnGateSchedule"; schedule.value = globalSettings.vpn_gate_schedule_time || "03:30";
  const timezone = accessible(dom("input"), "VPNGate 调度时区"); timezone.id = "globalVpnGateTimezone"; timezone.placeholder = "时区，例如 Asia/Shanghai"; timezone.value = globalSettings.vpn_gate_timezone || "local";
  const grace = accessible(dom("input"), "旧节点快照宽限小时"); grace.type = "number"; grace.min = "1"; grace.max = "168"; grace.id = "globalOldSnapshotGraceHours"; grace.placeholder = "旧快照宽限小时"; grace.value = globalSettings.old_snapshot_grace_hours || 48;
  const vpnGateUrl = accessible(dom("input"), "VPNGate API URL"); vpnGateUrl.id = "globalVpnGateApiUrl"; vpnGateUrl.placeholder = "VPNGate API URL"; vpnGateUrl.value = globalSettings.vpn_gate_api_url || "";
  const vpnRetry = accessible(dom("input"), "VPNGate 重试退避秒数"); vpnRetry.id = "globalVpnGateRetryBackoff"; vpnRetry.placeholder = "VPNGate 重试退避秒数，如 300,900,1800"; vpnRetry.value = (globalSettings.vpn_gate_retry_backoff_seconds || []).join(",");
  const instanceRetry = accessible(dom("input"), "实例连接重试退避秒数"); instanceRetry.id = "globalInstanceRetryBackoff"; instanceRetry.placeholder = "实例连接重试退避秒数，如 60,300,900"; instanceRetry.value = (globalSettings.instance_retry_backoff_seconds || []).join(",");
  const candidateLimit = accessible(dom("input"), "每轮连接候选节点数量"); candidateLimit.id = "globalConnectionCandidateLimit"; candidateLimit.type = "number"; candidateLimit.min = "1"; candidateLimit.max = "10"; candidateLimit.placeholder = "连接候选节点数量"; candidateLimit.value = globalSettings.connection_candidate_limit || 3;
  settings.append(schedulerLabel, schedule, timezone, grace, vpnGateUrl, vpnRetry, instanceRetry, candidateLimit);
  const enabled = dom("input"); enabled.type = "checkbox"; enabled.id = "globalScamalyticsEnabled"; enabled.checked = Boolean(globalSettings.scamalytics_enabled);
  const label = dom("label", "muted", "启用 Scamalytics"); label.prepend(enabled);
  const username = accessible(dom("input"), "Scamalytics 用户名"); username.id = "globalScamalyticsUsername"; username.placeholder = "用户名"; username.value = globalSettings.scamalytics_username || "";
  const dailyQuota = accessible(dom("input"), "Scamalytics 每日请求配额"); dailyQuota.type = "number"; dailyQuota.min = "1"; dailyQuota.max = "1000000"; dailyQuota.id = "globalScamalyticsDailyQuota"; dailyQuota.placeholder = "每日请求配额"; dailyQuota.value = globalSettings.scamalytics_daily_quota || 1000;
  const rateLimit = accessible(dom("input"), "Scamalytics 每分钟请求上限"); rateLimit.type = "number"; rateLimit.min = "1"; rateLimit.max = "10000"; rateLimit.id = "globalScamalyticsRateLimit"; rateLimit.placeholder = "每分钟请求上限"; rateLimit.value = globalSettings.scamalytics_rate_limit_per_minute || 30;
  const cacheDays = accessible(dom("input"), "Scamalytics 缓存天数"); cacheDays.type = "number"; cacheDays.min = "1"; cacheDays.max = "90"; cacheDays.id = "globalScamalyticsCacheDays"; cacheDays.placeholder = "缓存天数"; cacheDays.value = globalSettings.scamalytics_cache_ttl_days || 7;
  const scamUrl = accessible(dom("input"), "Scamalytics API URL"); scamUrl.id = "globalScamalyticsApiUrl"; scamUrl.placeholder = "Scamalytics API URL"; scamUrl.value = globalSettings.scamalytics_api_url || "";
  const timeout = accessible(dom("input"), "Scamalytics 请求超时秒数"); timeout.type = "number"; timeout.min = "1"; timeout.max = "120"; timeout.id = "globalScamalyticsTimeout"; timeout.placeholder = "请求超时（秒）"; timeout.value = globalSettings.scamalytics_timeout_seconds || 8;
  const risk = accessible(dom("input"), "Scamalytics 高风险阈值"); risk.type = "number"; risk.min = "0"; risk.max = "100"; risk.id = "globalScamalyticsRisk"; risk.placeholder = "高风险阈值"; risk.value = globalSettings.scamalytics_risk_threshold ?? 70;
  const key = accessible(dom("input"), "Scamalytics API Key"); key.id = "globalScamalyticsKey"; key.type = "password"; key.placeholder = globalSettings.scamalytics_api_key_masked ? "API Key 已保存（留空保持不变）" : "API Key";
  const save = actionButton("保存质量配置", "save-global-settings");
  const jsonRetention = accessible(dom("input"), "JSON 日志保留天数"); jsonRetention.type = "number"; jsonRetention.min = "1"; jsonRetention.max = "90"; jsonRetention.id = "globalJsonLogRetention"; jsonRetention.placeholder = "JSON 日志保留天数"; jsonRetention.value = globalSettings.json_log_retention_days || 7;
  const textMaxMiB = accessible(dom("input"), "文本日志单文件大小 MiB"); textMaxMiB.type = "number"; textMaxMiB.min = "1"; textMaxMiB.max = "1024"; textMaxMiB.id = "globalTextLogMaxMiB"; textMaxMiB.placeholder = "文本日志 MiB"; textMaxMiB.value = Math.round((globalSettings.text_log_max_bytes || 10485760) / 1048576);
  const textBackups = accessible(dom("input"), "文本日志保留份数"); textBackups.type = "number"; textBackups.min = "1"; textBackups.max = "32"; textBackups.id = "globalTextLogBackups"; textBackups.placeholder = "文本日志保留份数"; textBackups.value = globalSettings.text_log_backup_count || 7;
  settings.append(label, username, scamUrl, timeout, dailyQuota, rateLimit, cacheDays, risk, key, jsonRetention, textMaxMiB, textBackups, save, actionButton("测试质量配置", "test-global-scamalytics"));
  const restore = dom("div", "global-settings-form");
  const file = accessible(dom("input"), "选择 AimiliVPN JSON 备份文件"); file.type = "file"; file.accept = "application/json,.json"; file.id = "globalBackupFile";
  restore.append(file, actionButton("预览恢复", "preview-global-backup"), actionButton("确认恢复", "restore-global-backup", {}, "danger"));
  const restorePreview = dom("pre", ""); restorePreview.id = "globalBackupPreview"; restorePreview.hidden = true;
  card.append(title, details, toolbar, settings, restore, restorePreview);
  return card;
}

function showGlobalNodes(preset = {}) {
  globalNodePreset.availability = String(preset.availability ?? globalNodePreset.availability ?? "");
  globalNodePreset.riskLevel = String(preset.riskLevel ?? globalNodePreset.riskLevel ?? "");
  globalNodePreset.minRisk = String(preset.minRisk ?? globalNodePreset.minRisk ?? "");
  globalNodePreset.maxRisk = String(preset.maxRisk ?? globalNodePreset.maxRisk ?? "");
  currentInstanceId = null;
  activateTab("tabGlobalNodes");
  const card = dom("div", "card");
  card.append(dom("h2", "", "全局节点中心"));
  card.append(dom("div", "muted", `共 ${globalNodes.length} 个节点 · 快照更新时间 ${formatTimestamp(globalTask.snapshot_updated_at)}`));
  const filters = dom("div", "global-settings-form");
  const keyword = accessible(dom("input"), "按 IP 或国家地区搜索节点"); keyword.placeholder = "搜索 IP 或国家/地区";
  const country = accessible(dom("select"), "按国家或地区筛选节点");
  country.append(new Option("全部国家/地区", ""));
  [...new Set(globalNodes.map((node) => node.country || node.country_short).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right))
    .forEach((value) => country.append(new Option(value, value)));
  const qualityStatus = accessible(dom("select"), "按质量状态筛选节点");
  qualityStatus.append(
    new Option("全部质量状态", ""),
    new Option("已完成", "ok"),
    new Option("待处理", "pending"),
    new Option("失败", "failed"),
  );
  const availability = accessible(dom("select"), "按可用性筛选节点");
  availability.append(
    new Option("全部可用性", ""),
    new Option("已连接", "active"),
    new Option("可用", "available"),
    new Option("不可用", "unavailable"),
    new Option("未检测", "not_checked"),
  );
  availability.value = globalNodePreset.availability;
  const riskLevel = accessible(dom("select"), "按风险等级筛选节点");
  riskLevel.append(
    new Option("全部风险等级", ""),
    new Option("低风险", "low"),
    new Option("中风险", "medium"),
    new Option("高风险", "high"),
    new Option("未知风险", "unknown"),
  );
  riskLevel.value = globalNodePreset.riskLevel;
  const cacheState = accessible(dom("select"), "按缓存状态筛选节点");
  cacheState.append(
    new Option("全部缓存状态", ""),
    new Option("缓存有效", "valid"),
    new Option("缓存过期", "expired"),
    new Option("无缓存", "missing"),
  );
  const minLatency = accessible(dom("input"), "最小延迟毫秒"); minLatency.type = "number"; minLatency.min = "0"; minLatency.placeholder = "最小延迟 ms";
  const maxLatency = accessible(dom("input"), "最大延迟毫秒"); maxLatency.type = "number"; maxLatency.min = "0"; maxLatency.placeholder = "最大延迟 ms";
  const minRisk = accessible(dom("input"), "最小风险分"); minRisk.type = "number"; minRisk.min = "0"; minRisk.max = "100"; minRisk.placeholder = "最小风险分"; minRisk.value = globalNodePreset.minRisk;
  const maxRisk = accessible(dom("input"), "最大风险分"); maxRisk.type = "number"; maxRisk.min = "0"; maxRisk.max = "100"; maxRisk.placeholder = "最大风险分"; maxRisk.value = globalNodePreset.maxRisk;
  const updatedAfter = accessible(dom("input"), "节点更新时间不早于"); updatedAfter.type = "datetime-local";
  const updatedBefore = accessible(dom("input"), "节点更新时间不晚于"); updatedBefore.type = "datetime-local";
  const sort = accessible(dom("select"), "节点排序方式");
  sort.append(
    new Option("默认排序", "default"),
    new Option("延迟从低到高", "latency"),
    new Option("VPNGate 评分从高到低", "score"),
    new Option("风险从低到高", "risk"),
    new Option("更新时间从新到旧", "updated"),
  );
  const resetFilters = actionButton("重置筛选", "reset-global-node-filters");
  filters.append(keyword, country, availability, qualityStatus, riskLevel, minRisk, maxRisk, cacheState, minLatency, maxLatency, updatedAfter, updatedBefore, sort, resetFilters);
  const resultSummary = dom("div", "filter-summary");
  card.append(filters, resultSummary);
  const [nodesTable, body] = table(["IP", "国家/地区", "VPNGate 评分", "风险分数/等级", "检测来源", "检测时间", "缓存状态", "质量状态", "配置"]);
  const renderRows = () => {
    const query = keyword.value.trim().toLowerCase();
    const filtered = globalNodes.filter((node) => {
      const quality = node.quality_result || {};
      const status = quality.status || "pending";
      const availabilityValue = node.active ? "active" : String(node.probe_status || "not_checked");
      const location = node.country || node.country_short || "";
      const address = node.server_ip || node.ip || "";
      const latency = Number(node.latency_ms || node.ping || 0);
      const cacheExpiresAt = asEpoch(quality.cache_expires_at);
      const checkedAt = asEpoch(node.updated_at || quality.checked_at);
      const now = Date.now() / 1000;
      const cache = cacheExpiresAt ? (cacheExpiresAt > now ? "valid" : "expired") : "missing";
      const after = asEpoch(updatedAfter.value);
      const before = asEpoch(updatedBefore.value);
      const riskScore = numericRiskScore(quality);
      const hasRiskScore = Number.isFinite(riskScore);
      return (!query || `${address} ${location}`.toLowerCase().includes(query))
        && (!country.value || location === country.value)
        && (!availability.value || availabilityValue === availability.value)
        && (!qualityStatus.value || status === qualityStatus.value)
        && (!riskLevel.value || riskBucket(quality) === riskLevel.value)
        && (!minRisk.value || (hasRiskScore && riskScore >= Number(minRisk.value)))
        && (!maxRisk.value || (hasRiskScore && riskScore <= Number(maxRisk.value)))
        && (!cacheState.value || cache === cacheState.value)
        && (!minLatency.value || latency >= Number(minLatency.value))
        && (!maxLatency.value || latency <= Number(maxLatency.value))
        && (!after || checkedAt >= after)
        && (!before || checkedAt <= before);
    });
    filtered.sort((left, right) => {
      const leftQuality = left.quality_result || {};
      const rightQuality = right.quality_result || {};
      if (sort.value === "latency") return Number(left.latency_ms || left.ping || Infinity) - Number(right.latency_ms || right.ping || Infinity);
      if (sort.value === "score") return Number(right.score || 0) - Number(left.score || 0);
      if (sort.value === "risk") {
        const leftRisk = numericRiskScore(leftQuality);
        const rightRisk = numericRiskScore(rightQuality);
        const leftValue = Number.isFinite(leftRisk) ? leftRisk : Number.POSITIVE_INFINITY;
        const rightValue = Number.isFinite(rightRisk) ? rightRisk : Number.POSITIVE_INFINITY;
        return leftValue - rightValue;
      }
      if (sort.value === "updated") return asEpoch(right.updated_at || rightQuality.checked_at) - asEpoch(left.updated_at || leftQuality.checked_at);
      return 0;
    });
    body.replaceChildren();
    resultSummary.textContent = `当前结果 ${filtered.length} / ${globalNodes.length} 个节点`;
    if (!filtered.length) {
      const row = dom("tr");
      const empty = dom("td", "empty-state", globalNodes.length ? "没有符合筛选条件的节点。" : "当前没有全局节点快照，请先执行更新。");
      empty.colSpan = 9;
      row.append(empty);
      body.append(row);
      return;
    }
    for (const node of filtered) {
      const quality = node.quality_result || {};
      const cacheExpiresAt = Number(quality.cache_expires_at || 0);
      const riskScore = numericRiskScore(quality);
      const risk = !Number.isFinite(riskScore)
        ? "未检测"
        : `${riskScore}${quality.risk_level ? ` / ${quality.risk_level}` : ""}`;
      const row = dom("tr");
      row.append(
        cell(node.server_ip || node.ip),
        cell(node.country || node.country_short),
        cell(node.score),
        cell(`${risk}${node.snapshot_country_stale ? "（旧快照）" : ""}`),
        cell(`${quality.risk_provider || quality.provider || "-"}${quality.proxy_detected ? " · 代理" : ""}${quality.datacenter_detected ? " · 数据中心" : ""}`),
        cell(quality.checked_at ? formatTimestamp(quality.checked_at) : "未检测"),
        cell(cacheExpiresAt ? (cacheExpiresAt > Date.now() / 1000 ? "有效" : "已过期") : "无缓存"),
        cell(quality.status === "ok" ? "已完成" : (quality.status || "待处理")),
        cell(node.config_file ? "已配置" : "缺少配置"),
      );
      body.append(row);
    }
  };
  keyword.addEventListener("input", renderRows);
  country.addEventListener("change", renderRows);
  availability.addEventListener("change", renderRows);
  qualityStatus.addEventListener("change", renderRows);
  riskLevel.addEventListener("change", renderRows);
  minRisk.addEventListener("input", renderRows);
  maxRisk.addEventListener("input", renderRows);
  cacheState.addEventListener("change", renderRows);
  minLatency.addEventListener("input", renderRows);
  maxLatency.addEventListener("input", renderRows);
  updatedAfter.addEventListener("change", renderRows);
  updatedBefore.addEventListener("change", renderRows);
  sort.addEventListener("change", renderRows);
  availability.addEventListener("change", () => { globalNodePreset.availability = availability.value; });
  riskLevel.addEventListener("change", () => { globalNodePreset.riskLevel = riskLevel.value; });
  minRisk.addEventListener("input", () => { globalNodePreset.minRisk = minRisk.value; });
  maxRisk.addEventListener("input", () => { globalNodePreset.maxRisk = maxRisk.value; });
  renderRows();
  card.append(nodesTable);
  el("content").replaceChildren(card);
}

function showGlobalTasks(options = {}) {
  currentInstanceId = null;
  activateTab("tabGlobalTasks");
  const taskCard = dom("div", "card");
  taskCard.append(dom("h2", "", "全局任务与质量"));
  taskCard.append(dom("div", "muted", `状态：${globalTask.status || "未执行"} · 下次运行：${formatTimestamp(globalTask.next_run_at)} · 有效质量缓存：${globalTask.quality_cache_count || 0}`));
  const metrics = globalTask.quality_metrics || {};
  taskCard.append(dom("div", "quality-summary", `今日配额 ${metrics.quota || "未设置"} · 缓存命中 ${metrics.cache_hits || 0} · API 请求 ${metrics.requests || 0} · 成功 ${metrics.successes || 0} · 失败 ${metrics.failures || 0} · 剩余 ${metrics.remaining === null || metrics.remaining === undefined ? "未设置" : metrics.remaining} · 当前积压 ${(globalTask.quality_queue || []).length}`));
  const history = Array.isArray(globalTask.history) ? globalTask.history : [];
  const [historyTable, historyBody] = table(["时间", "状态", "原因", "节点数", "错误"]);
  for (const item of history.slice().reverse()) {
    const row = dom("tr");
    row.append(cell(formatTimestamp(item.at || item.created_at)), cell(item.status), cell(item.reason), cell(item.node_count), cell(item.error_code));
    historyBody.append(row);
  }
  if (!history.length) {
    const row = dom("tr");
    const empty = dom("td", "empty-state", "暂无任务历史。");
    empty.colSpan = 5;
    row.append(empty);
    historyBody.append(row);
  }
  taskCard.append(dom("h3", "", "任务历史"), historyTable);

  const queueCard = dom("div", options.focusQueue ? "card focus-target" : "card");
  queueCard.append(dom("h3", "", "Scamalytics 待处理队列"));
  const queue = Array.isArray(globalTask.quality_queue) ? globalTask.quality_queue : [];
  const [queueTable, queueBody] = table(["IP", "状态", "尝试次数", "下次重试", "错误"]);
  for (const item of queue) {
    const row = dom("tr");
    row.append(cell(item.ip), cell(item.status), cell(item.attempts), cell(formatTimestamp(item.next_attempt_at)), cell(qualityQueueErrorMessage(item.last_error)));
    queueBody.append(row);
  }
  if (!queue.length) {
    const row = dom("tr");
    const empty = dom("td", "empty-state", "当前没有待处理质量请求。");
    empty.colSpan = 5;
    row.append(empty);
    queueBody.append(row);
  }
  queueCard.append(queueTable);
  el("content").replaceChildren(taskCard, queueCard);
  if (options.focusQueue && typeof queueCard.scrollIntoView === "function") {
    queueCard.scrollIntoView({ block: "start" });
  }
}

function redactLogText(value) {
  return String(value || "")
    .replace(/((?:api[_-]?key|token|password|secret|credential)\s*[=:]\s*["']?)[^\s,"'}]+/gi, "$1[已脱敏]")
    .replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, "$1[已脱敏]@");
}

function downloadRedactedLogs(entries) {
  const lines = entries.map(item => JSON.stringify({
    timestamp: item.timestamp || "",
    instance: item.instance || "global",
    level: item.level || "INFO",
    module: item.module || "",
    event: item.event || "",
    message: redactLogText(item.message),
    suppressed_count: Number(item.suppressed_count || 0),
  }));
  const blob = new Blob([`${lines.join("\n")}\n`], { type: "application/x-ndjson;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `aimilivpn-redacted-logs-${new Date().toISOString().slice(0, 10)}.ndjson`;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function showGlobalLogsV103(presetInstance = "") {
  currentInstanceId = null;
  activateTab("tabGlobalLogs");
  try {
    const data = await api("global/logs");
    const security = data.security || {};
    const allEntries = [];
    for (const item of (Array.isArray(data.global_history) ? data.global_history : [])) {
      allEntries.push({ ...item, instance: "global", level: item.level || "INFO", module: item.module || "global-task", event: item.event || item.status || "task" });
    }
    for (const group of (Array.isArray(data.instances) ? data.instances : [])) {
      for (const item of (Array.isArray(group.logs) ? group.logs : [])) {
        allEntries.push({ ...item, instance: group.id || "-", country: group.country || "", event: item.event || item.event_type || "log" });
      }
    }
    allEntries.sort((left, right) => asEpoch(right.timestamp || right.at || right.created_at) - asEpoch(left.timestamp || left.at || left.created_at));

    const card = dom("div", "card");
    card.append(dom("h2", "", "日志与安全"));
    card.append(dom("div", "muted", `存储后端：${security.storage_backend || "-"} · 日志保留 ${security.log_retention_days || "-"} 天 · 文本轮转 ${security.text_log_backup_count || "-"} 份`));
    const storageHealth = security.storage_health || {};
    const migration = security.last_migration || {};
    card.append(dom("div", "muted", `数据库健康：${storageHealth.ok === false ? "异常" : "正常"} · 校验 ${storageHealth.quick_check || "-"} · 最近导入节点 ${migration.nodes || 0}、质量结果 ${migration.quality || 0}`));
    const latestBackup = security.latest_backup || {};
    card.append(dom("div", "muted", latestBackup.path
      ? `最近备份：${latestBackup.path} · ${formatTimestamp(latestBackup.updated_at)} · 校验${latestBackup.validated ? "通过" : "失败"} · SHA-256 ${latestBackup.checksum || "-"}`
      : "最近备份：暂无记录"));
    const lastRestore = security.last_restore || {};
    card.append(dom("div", "muted", lastRestore.at
      ? `最近恢复：${formatTimestamp(lastRestore.at)} · ${lastRestore.ok ? "成功" : "失败"} · 恢复前快照 ${lastRestore.backup_before_restore || "-"} · SHA-256 ${lastRestore.checksum || "-"}`
      : "最近恢复：本次运行期间暂无记录"));
    const instanceStorage = Array.isArray(security.instance_storage) ? security.instance_storage : [];
    const [storageTable, storageBody] = table(["实例", "后端", "健康", "迁移时间", "迁移结果", "最近迁移备份", "条数", "SHA-256 摘要"]);
    for (const item of instanceStorage) {
      const summary = item.migration || {};
      const checksums = Array.isArray(summary.documents)
        ? summary.documents.map(document => `${document.kind}: ${document.checksum}`).join("\n")
        : "-";
      const row = dom("tr");
      const migrationResult = summary.result === "success" ? "成功" : (summary.result ? "失败" : "无迁移记录");
      row.append(cell(item.id), cell(item.backend), cell(item.ok ? (item.quick_check || "正常") : (item.quick_check || "异常")), cell(summary.migrated_at ? formatTimestamp(summary.migrated_at) : "-"), cell(migrationResult), cell(summary.backup_dir || "无迁移记录"), cell(summary.total_count ?? "-"), cell(checksums));
      storageBody.append(row);
    }
    if (!instanceStorage.length) {
      const row = dom("tr"); const empty = dom("td", "empty-state", "暂无实例存储状态。"); empty.colSpan = 8; row.append(empty); storageBody.append(row);
    }
    card.append(dom("h3", "", "实例存储与迁移"), storageTable);
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "本地时区";
    card.append(dom("div", "muted", `日志时间按当前浏览器时区显示：${timezone}`));
    const filters = dom("div", "global-settings-form");
    const instance = accessible(dom("select"), "按实例筛选日志"); instance.append(new Option("全部实例", ""), ...[...new Set(allEntries.map(item => item.instance).filter(Boolean))].sort().map(value => new Option(value, value)));
    instance.value = presetInstance;
    const level = accessible(dom("select"), "按级别筛选日志"); level.append(new Option("全部级别", ""), ...[...new Set(allEntries.map(item => item.level).filter(Boolean))].sort().map(value => new Option(value, value)));
    const module = accessible(dom("input"), "按模块筛选日志"); module.placeholder = "模块筛选";
    const event = accessible(dom("input"), "按事件筛选日志"); event.placeholder = "事件筛选";
    const search = accessible(dom("input"), "搜索已脱敏日志"); search.placeholder = "搜索已脱敏日志";
    const after = accessible(dom("input"), "日志开始时间"); after.type = "datetime-local";
    const before = accessible(dom("input"), "日志结束时间"); before.type = "datetime-local";
    const download = actionButton("导出筛选结果（再次脱敏）", "", {}, "primary");
    filters.append(instance, level, module, event, search, after, before, download);
    card.append(filters);
    const [logTable, body] = table(["时间", "实例", "级别", "模块", "事件", "重复抑制", "消息"]);
    let currentFiltered = [];
    const renderRows = () => {
      const query = search.value.trim().toLowerCase();
      const filtered = allEntries.filter(item => {
        const message = redactLogText(item.message);
        const timestamp = asEpoch(item.timestamp || item.at || item.created_at);
        const afterTimestamp = asEpoch(after.value);
        const beforeTimestamp = asEpoch(before.value);
        return (!instance.value || item.instance === instance.value)
          && (!level.value || String(item.level || "") === level.value)
          && (!module.value || String(item.module || "").toLowerCase().includes(module.value.trim().toLowerCase()))
          && (!event.value || String(item.event || "").toLowerCase().includes(event.value.trim().toLowerCase()))
          && (!query || `${item.instance} ${item.level} ${item.module} ${item.event} ${message}`.toLowerCase().includes(query))
          && (!afterTimestamp || timestamp >= afterTimestamp)
          && (!beforeTimestamp || timestamp <= beforeTimestamp);
      });
      currentFiltered = filtered;
      body.replaceChildren();
      for (const item of filtered) {
        const row = dom("tr");
        row.append(
          cell(formatTimestamp(item.timestamp || item.at || item.created_at)),
          cell(item.instance), cell(item.level || "INFO"), cell(item.module), cell(item.event),
          cell(item.suppressed_count ? `${item.suppressed_count} 次` : "-"), cell(redactLogText(item.message)),
        );
        body.append(row);
      }
      if (!filtered.length) {
        const row = dom("tr"); const empty = dom("td", "empty-state", "没有符合筛选条件的日志。"); empty.colSpan = 7; row.append(empty); body.append(row);
      }
    };
    download.addEventListener("click", () => downloadRedactedLogs(currentFiltered));
    [instance, level].forEach(control => control.addEventListener("change", renderRows));
    [module, event, search].forEach(control => control.addEventListener("input", renderRows));
    [after, before].forEach(control => control.addEventListener("change", renderRows));
    renderRows();
    card.append(logTable);
    el("content").replaceChildren(card);
  } catch (error) {
    showError(error.message);
  }
}

function formatTimestamp(value) {
  if (!value) return "未计划";
  const numeric = Number(value);
  const date = Number.isFinite(numeric) ? new Date(numeric * 1000) : new Date(String(value));
  return Number.isNaN(date.getTime()) ? "未计划" : date.toLocaleString();
}

async function openInstance(instanceId) {
  currentInstanceId = instanceId;
  setOperation(`正在加载实例 ${instanceId}…`, "loading");
  const data = await api(`instances/${encodeURIComponent(instanceId)}/nodes`);
  const instance = data.state || {};
  const nodes = Array.isArray(data.nodes) ? data.nodes : [];
  const summary = dom("div", "card");
  const heading = dom("div", "row");
  const title = dom("h2", "", `${instance.country || "-"} `);
  title.append(dom("span", "pill", instanceId));
  heading.append(title, serviceStatus(instance));
  const toolbar = dom("div", "toolbar");
  toolbar.append(
    actionButton("刷新节点", "backend", { instanceId, backendAction: "refresh_nodes" }, "primary"),
    actionButton("测试代理", "backend", { instanceId, backendAction: "test_proxy" }),
    actionButton("断开连接", "backend", { instanceId, backendAction: "disconnect" }),
    actionButton(instance.service_active ? "停止服务" : "启动服务", "service", {
      instanceId,
      serviceAction: instance.service_active ? "stop" : "start",
    }),
    actionButton("重启服务", "service", { instanceId, serviceAction: "restart" }),
    actionButton("查看日志", "logs", { instanceId }),
    actionButton("删除实例", "delete", { instanceId }, "danger"),
  );
  summary.append(
    heading,
    dom("div", "muted", resourceSummary(instance)),
    dom("div", "muted", stateRoutingSummary(instance.state || {})),
    dom("div", "muted", `最近切换/检查：${instance.state?.last_check_message || "-"}`),
    toolbar,
  );

  const nodeCard = dom("div", "card");
  const [nodesTable, body] = table(["状态", "IP", "国家/地区", "延迟", "质量", "操作"]);
  if (!nodes.length) {
    const row = dom("tr");
    const empty = dom("td", "empty-state", "暂无可用节点。");
    empty.colSpan = 6;
    row.append(empty);
    body.append(row);
  }
  for (const node of nodes) {
    const row = dom("tr");
    const actions = dom("td");
    actions.append(
      actionButton("连接", "connect", { instanceId, nodeId: node.id }),
      actionButton("测试", "test-node", { instanceId, nodeId: node.id }),
    );
    row.append(
      cell(translateNodeStatus(node.active ? "active" : node.probe_status)),
      cell(node.ip || node.remote_host),
      cell(node.country || node.country_short),
      cell(node.latency_ms || node.ping),
      cell(node.quality),
      actions,
    );
    body.append(row);
  }
  nodeCard.append(nodesTable);
  el("content").replaceChildren(summary, nodeCard);
  setOperation(`正在查看 ${instanceId}`, "ok");
}

async function runOperation(button, label, operation) {
  const original = button ? button.textContent : "";
  if (button) {
    button.disabled = true;
    button.textContent = label;
  }
  setOperation(label, "loading");
  try {
    const result = await operation();
    setOperation(
      result === false ? "操作已取消" : (typeof result === "string" ? result : "操作完成"),
      "ok",
    );
  } catch (error) {
    showError(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

async function refreshGlobal(button) {
  await runOperation(button, "正在更新全局节点…", async () => {
    await api("global/refresh", { method: "POST" });
    await load();
  });
}

function parseBackoffInput(value, fallback) {
  const text = String(value || "").trim();
  if (!text) return fallback;
  const values = text.split(",").map(item => Number(item.trim()));
  if (!values.length || values.some(item => !Number.isInteger(item) || item <= 0)) {
    throw new Error("重试退避必须是以逗号分隔的正整数秒数");
  }
  return values;
}

async function saveGlobalSettings(button) {
  const payload = {
    vpn_gate_enabled: Boolean(el("globalVpnGateEnabled")?.checked),
    vpn_gate_schedule_time: el("globalVpnGateSchedule")?.value || "03:30",
    vpn_gate_timezone: el("globalVpnGateTimezone")?.value || "local",
    old_snapshot_grace_hours: Number(el("globalOldSnapshotGraceHours")?.value || 48),
    vpn_gate_api_url: el("globalVpnGateApiUrl")?.value || "",
    vpn_gate_retry_backoff_seconds: parseBackoffInput(
      el("globalVpnGateRetryBackoff")?.value,
      globalSettings.vpn_gate_retry_backoff_seconds || [300, 900, 1800, 3600],
    ),
    scamalytics_enabled: Boolean(el("globalScamalyticsEnabled")?.checked),
    scamalytics_username: el("globalScamalyticsUsername")?.value || "",
    scamalytics_api_url: el("globalScamalyticsApiUrl")?.value || "",
    scamalytics_timeout_seconds: Number(el("globalScamalyticsTimeout")?.value || 8),
    scamalytics_daily_quota: Number(el("globalScamalyticsDailyQuota")?.value || 1000),
    scamalytics_rate_limit_per_minute: Number(el("globalScamalyticsRateLimit")?.value || 30),
    scamalytics_cache_ttl_days: Number(el("globalScamalyticsCacheDays")?.value || 7),
    scamalytics_risk_threshold: Number(el("globalScamalyticsRisk")?.value || 70),
    instance_retry_backoff_seconds: parseBackoffInput(
      el("globalInstanceRetryBackoff")?.value,
      globalSettings.instance_retry_backoff_seconds || [60, 300, 900, 1800],
    ),
    connection_candidate_limit: Number(el("globalConnectionCandidateLimit")?.value || 3),
    json_log_retention_days: Number(el("globalJsonLogRetention")?.value || 7),
    text_log_max_bytes: Number(el("globalTextLogMaxMiB")?.value || 10) * 1024 * 1024,
    text_log_backup_count: Number(el("globalTextLogBackups")?.value || 7),
  };
  const apiKey = el("globalScamalyticsKey")?.value || "";
  if (apiKey) payload["scamalytics_api_key"] = apiKey;
  await runOperation(button, "正在保存全局配置…", async () => {
    await api("global/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await load();
    return "全局配置已保存；VPNGate 设置立即生效，实例连接参数将在相关服务重启后生效";
  });
}

async function testGlobalScamalytics(button) {
  await runOperation(button, "正在测试质量配置…", async () => {
    await api("global/scamalytics/test", { method: "POST" });
  });
}

let pendingGlobalBackup = null;
let pendingGlobalPreview = null;

async function readGlobalBackup() {
  const file = el("globalBackupFile")?.files?.[0];
  if (!file) throw new Error("请选择 JSON 备份文件");
  return JSON.parse(await file.text());
}

async function previewGlobalBackup(button) {
  await runOperation(button, "正在校验备份…", async () => {
    pendingGlobalBackup = await readGlobalBackup();
    const result = await api("global/backup/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup: pendingGlobalBackup }),
    });
    const preview = result.preview || {};
    pendingGlobalPreview = preview;
    const output = el("globalBackupPreview");
    if (output) {
      const lines = [];
      for (const [label, key] of [["新增", "added"], ["修改", "modified"], ["删除", "removed"], ["忽略", "ignored"]]) {
        const items = Array.isArray(preview[key]) ? preview[key] : [];
        lines.push(`${label}（${items.length}）`);
        for (const item of items) lines.push(`  - ${item.path || "未知字段"}${item.reason ? `：${item.reason}` : ""}`);
      }
      output.textContent = lines.join("\n");
      output.hidden = false;
    }
    setOperation(`预检完成：${preview.change_count || 0} 项变更，请确认后恢复`, preview.changed ? "loading" : "ok");
  });
}

async function restoreGlobalBackup(button) {
  await runOperation(button, "正在恢复配置…", async () => {
    if (!pendingGlobalBackup || !pendingGlobalPreview) throw new Error("请先预览并校验当前备份文件");
    if (!confirm("恢复会先自动备份当前状态，并同步实例清单。删除项将停止对应实例但保留数据，确定继续吗？")) return false;
    let confirmDeletions = false;
    if (pendingGlobalPreview?.requires_deletion_confirmation) {
      confirmDeletions = confirm("差异预览包含删除项。是否单独确认执行这些删除？实例数据将保留。");
      if (!confirmDeletions) return false;
    }
    const result = await api("global/backup/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup: pendingGlobalBackup, confirmed: true, confirm_deletions: confirmDeletions }),
    });
    pendingGlobalBackup = null;
    pendingGlobalPreview = null;
    await load();
    return `恢复报告：成功；恢复前快照 ${result.backup_before_restore || "已创建"}；SHA-256 ${result.checksum || "已校验"}`;
  });
}

async function createInstance(button) {
  const select = el("catalogCountry");
  if (!select || !select.value) return;
  const item = instanceCatalog.find(entry => entry.country === select.value);
  if (!item) return;
  const impact = `将创建并启动 ${item.country} 实例，使用 ${resourceSummary(item)}。系统会生成受管服务、环境配置和独立数据目录。`;
  if (!confirm(`${impact}\n\n确定继续吗？`)) {
    setOperation("已取消创建实例", "ok");
    return;
  }
  await runOperation(button, `正在创建 ${item.country}…`, async () => {
    await api("instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country: item.country, id: item.id }),
    });
    await load();
  });
}

async function serviceInstance(instanceId, action, button) {
  const instance = instanceList.find(item => item.id === instanceId);
  const labels = { start: "启动", stop: "停止", restart: "重启" };
  const impacts = {
    start: "将启动受管服务并恢复该实例的连接与代理监听。",
    stop: "将停止受管服务，并中断该实例当前 VPN 和代理连接。",
    restart: "将短暂中断该实例当前 VPN 和代理连接，然后重新加载配置。",
  };
  const label = labels[action];
  if (!instance || !label) {
    showError("实例或服务操作无效");
    return;
  }
  if (!confirm(`${label}实例 ${instanceId}？\n\n影响范围：${impacts[action]}\n受管资源：${resourceSummary(instance)}`)) {
    setOperation(`已取消${label}实例`, "ok");
    return;
  }
  await mutateInstance(button, `instances/${encodeURIComponent(instanceId)}/service`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
}

async function deleteInstance(instanceId, button) {
  if (!confirm(`确定停止并删除实例 ${instanceId}？默认保留数据。`)) return;
  const confirmation = prompt(`请输入 ${instanceId} 以确认删除：`) || "";
  if (confirmation !== instanceId) {
    setOperation("已取消删除：确认内容不匹配", "bad");
    return;
  }
  const purgeData = confirm("是否同时永久删除此实例数据？取消则保留数据。");
  let purgeConfirmation = "";
  if (purgeData) {
    purgeConfirmation = prompt(`请输入 purge:${instanceId} 以确认永久删除数据：`) || "";
    if (purgeConfirmation !== `purge:${instanceId}`) {
      setOperation("已取消删除：数据清理确认内容不匹配", "bad");
      return;
    }
  }
  await runOperation(button, `正在删除 ${instanceId}…`, async () => {
    await api(`instances/${encodeURIComponent(instanceId)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        confirmation: instanceId,
        retain_data: !purgeData,
        purge_data_confirmation: purgeConfirmation,
      }),
    });
    await load();
  });
}

async function mutateInstance(button, path, options = {}) {
  await runOperation(button, "处理中…", async () => {
    await api(path, options);
    if (currentInstanceId) await openInstance(currentInstanceId);
    else await load();
  });
}

async function showLogs(instanceId) {
  await showGlobalLogsV103(instanceId);
}

document.addEventListener("change", event => {
  if (event.target.id === "catalogCountry") updateCatalogResources();
  if (event.target.id === "globalBackupFile") {
    pendingGlobalBackup = null;
    pendingGlobalPreview = null;
    const output = el("globalBackupPreview");
    if (output) output.hidden = true;
  }
});

document.addEventListener("click", event => {
  const button = event.target.closest("button[data-console-action]");
  if (!button) return;
  const action = button.dataset.consoleAction;
  const instanceId = button.dataset.instanceId || "";
  const nodeId = button.dataset.nodeId || "";
  if (action === "overview") showOverview(button.dataset.instanceFilter || "all");
  else if (action === "global-nodes") showGlobalNodes({
    availability: button.dataset.resetFilters === "true" ? "" : button.dataset.availability,
    riskLevel: button.dataset.resetFilters === "true" ? "" : button.dataset.riskLevel,
    minRisk: button.dataset.resetFilters === "true" ? "" : button.dataset.minRisk,
    maxRisk: button.dataset.resetFilters === "true" ? "" : button.dataset.maxRisk,
  });
  else if (action === "reset-global-node-filters") showGlobalNodes({ availability: "", riskLevel: "", minRisk: "", maxRisk: "" });
  else if (action === "global-tasks") showGlobalTasks({ focusQueue: button.dataset.focusQueue === "true" });
  else if (action === "global-logs") showGlobalLogsV103();
  else if (action === "logout") logout();
  else if (action === "global-refresh") refreshGlobal(button);
  else if (action === "save-global-settings") saveGlobalSettings(button);
  else if (action === "test-global-scamalytics") testGlobalScamalytics(button);
  else if (action === "preview-global-backup") previewGlobalBackup(button);
  else if (action === "restore-global-backup") restoreGlobalBackup(button);
  else if (action === "open") openInstance(instanceId).catch(error => showError(error.message));
  else if (action === "create") createInstance(button);
  else if (action === "delete") deleteInstance(instanceId, button);
  else if (action === "logs") showLogs(instanceId);
  else if (action === "service") {
    serviceInstance(instanceId, button.dataset.serviceAction || "", button);
  } else if (action === "backend") {
    mutateInstance(button, `instances/${encodeURIComponent(instanceId)}/${button.dataset.backendAction || ""}`, { method: "POST" });
  } else if (["connect", "test-node"].includes(action)) {
    const backendAction = action === "connect" ? "connect" : "test_node";
    mutateInstance(button, `instances/${encodeURIComponent(instanceId)}/${backendAction}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: nodeId }),
    });
  }
});

async function logout() {
  await fetch("./api/logout", { method: "POST" });
  location.reload();
}

load().catch(error => showError(error.message));
