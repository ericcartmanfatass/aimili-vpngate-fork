let instanceList = [];
let instanceCatalog = [];
let currentInstanceId = null;
let globalSettings = {};
let globalTask = {};
let globalNodes = [];

function el(id) {
  return document.getElementById(id);
}

function dom(tag, className = "", text = undefined) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
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
  const nodesTab = actionButton("全局节点", "global-nodes", {}, "tab");
  nodesTab.id = "tabGlobalNodes";
  const tasksTab = actionButton("任务与质量", "global-tasks", {}, "tab");
  tasksTab.id = "tabGlobalTasks";
  tasksTab.textContent = "\\u4efb\\u52a1\\u4e0e\\u8d28\\u91cf";
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

function showOverview() {
  currentInstanceId = null;
  document.querySelectorAll(".tab").forEach(tab => tab.classList.remove("active"));
  el("tabOverview").classList.add("active");
  const card = dom("div", "card");
  card.append(dom("h2", "", "全局总览"));
  card.append(globalControlCard());
  if (!instanceList.length) {
    card.append(dom("div", "empty-state", "当前没有已管理实例。"));
    el("content").replaceChildren(card);
    return;
  }
  const [instancesTable, body] = table(["国家/地区", "服务", "代理", "TUN", "当前节点", "消息", "操作"]);
  for (const instance of instanceList) {
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
      cell(instance.state && instance.state.last_check_message),
      actionCell,
    );
    body.append(row);
  }
  card.append(instancesTable);
  el("content").replaceChildren(card);
}

function globalControlCard() {
  const card = dom("div", "card");
  const title = dom("div", "row");
  title.append(dom("h3", "", "全局任务"), dom("span", globalTask.status === "ok" ? "ok" : "muted", globalTask.status === "ok" ? "最近更新成功" : (globalTask.status || "未执行")));
  const details = dom("div", "muted", `节点 ${globalTask.node_count || 0} 个 · 计划时间 ${formatTimestamp(globalTask.next_run_at)} · Scamalytics ${globalSettings.scalamalytics_enabled ? "已启用" : "未启用"}`);
  const toolbar = dom("div", "toolbar");
  toolbar.append(
    actionButton("查看全局节点", "global-nodes"),
    actionButton("查看任务与质量", "global-tasks"),
  );
  toolbar.append(actionButton("立即更新节点", "global-refresh", {}, "primary"));
  const download = dom("a", "button");
  download.href = "./api/global/backup?type=config";
  download.download = "aimilivpn-v1.0.2-config.json";
  download.textContent = "下载配置备份";
  toolbar.append(download);
  const settings = dom("div", "global-settings-form");
  const schedulerEnabled = dom("input"); schedulerEnabled.type = "checkbox"; schedulerEnabled.id = "globalVpnGateEnabled"; schedulerEnabled.checked = globalSettings.vpn_gate_enabled !== false;
  const schedulerLabel = dom("label", "muted", "启用每日节点更新"); schedulerLabel.prepend(schedulerEnabled);
  const schedule = dom("input"); schedule.type = "time"; schedule.id = "globalVpnGateSchedule"; schedule.value = globalSettings.vpn_gate_schedule_time || "03:30";
  const timezone = dom("input"); timezone.id = "globalVpnGateTimezone"; timezone.placeholder = "时区，例如 Asia/Shanghai"; timezone.value = globalSettings.vpn_gate_timezone || "local";
  const grace = dom("input"); grace.type = "number"; grace.min = "1"; grace.max = "168"; grace.id = "globalOldSnapshotGraceHours"; grace.placeholder = "旧快照宽限小时"; grace.value = globalSettings.old_snapshot_grace_hours || 48;
  settings.append(schedulerLabel, schedule, timezone, grace);
  const enabled = dom("input"); enabled.type = "checkbox"; enabled.id = "globalScamalyticsEnabled"; enabled.checked = Boolean(globalSettings.scalamalytics_enabled);
  const label = dom("label", "muted", "启用 Scamalytics"); label.prepend(enabled);
  const username = dom("input"); username.id = "globalScamalyticsUsername"; username.placeholder = "用户名"; username.value = globalSettings.scalamalytics_username || "";
  const dailyQuota = dom("input"); dailyQuota.type = "number"; dailyQuota.min = "1"; dailyQuota.max = "1000000"; dailyQuota.id = "globalScamalyticsDailyQuota"; dailyQuota.placeholder = "每日请求配额"; dailyQuota.value = globalSettings.scalamalytics_daily_quota || 1000;
  const rateLimit = dom("input"); rateLimit.type = "number"; rateLimit.min = "1"; rateLimit.max = "10000"; rateLimit.id = "globalScamalyticsRateLimit"; rateLimit.placeholder = "每次批处理请求上限"; rateLimit.value = globalSettings.scalamalytics_rate_limit_per_minute || 30;
  const cacheDays = dom("input"); cacheDays.type = "number"; cacheDays.min = "1"; cacheDays.max = "90"; cacheDays.id = "globalScamalyticsCacheDays"; cacheDays.placeholder = "缓存天数"; cacheDays.value = globalSettings.scalamalytics_cache_ttl_days || 7;
  const key = dom("input"); key.id = "globalScamalyticsKey"; key.type = "password"; key.placeholder = globalSettings.scalamalytics_api_key_masked ? "API Key 已保存（留空保持不变）" : "API Key";
  const save = actionButton("保存质量配置", "save-global-settings");
  settings.append(label, username, dailyQuota, rateLimit, cacheDays, key, save, actionButton("测试质量配置", "test-global-scamalytics"));
  const restore = dom("div", "global-settings-form");
  const file = dom("input"); file.type = "file"; file.accept = "application/json,.json"; file.id = "globalBackupFile";
  restore.append(file, actionButton("预览恢复", "preview-global-backup"), actionButton("确认恢复", "restore-global-backup", {}, "danger"));
  card.append(title, details, toolbar, settings, restore);
  return card;
}

function showGlobalNodes() {
  currentInstanceId = null;
  activateTab("tabGlobalNodes");
  const card = dom("div", "card");
  card.append(dom("h2", "", "全局节点中心"));
  card.append(dom("div", "muted", `共 ${globalNodes.length} 个节点 · 快照更新时间 ${formatTimestamp(globalTask.snapshot_updated_at)}`));
  const [nodesTable, body] = table(["IP", "国家/地区", "VPNGate 评分", "Scamalytics 风险", "质量状态", "配置"]);
  if (!globalNodes.length) {
    const row = dom("tr");
    const empty = dom("td", "empty-state", "当前没有全局节点快照，请先执行更新。");
    empty.colSpan = 6;
    row.append(empty);
    body.append(row);
  }
  for (const node of globalNodes) {
    const quality = node.quality_result || {};
    const row = dom("tr");
    row.append(
      cell(node.server_ip || node.ip),
      cell(node.country || node.country_short),
      cell(node.score),
      cell(`${quality.risk_score === undefined ? "未检测" : quality.risk_score}${node.snapshot_country_stale ? "（旧快照）" : ""}`),
      cell(quality.status === "ok" ? "已完成" : (quality.status || "待处理")),
      cell(node.config_file ? "已配置" : "缺少配置"),
    );
    body.append(row);
  }
  card.append(nodesTable);
  el("content").replaceChildren(card);
}

function showGlobalTasks() {
  currentInstanceId = null;
  activateTab("tabGlobalTasks");
  const taskCard = dom("div", "card");
  taskCard.append(dom("h2", "", "全局任务与质量"));
  taskCard.append(dom("div", "muted", `状态：${globalTask.status || "未执行"} · 下次运行：${formatTimestamp(globalTask.next_run_at)} · 有效质量缓存：${globalTask.quality_cache_count || 0}`));
  const metrics = globalTask.quality_metrics || {};
  taskCard.append(dom("div", "quality-summary", `今日配额 ${metrics.quota || "未设置"} · 缓存命中 ${metrics.cache_hits || 0} · API 请求 ${metrics.requests || 0} · 失败 ${metrics.failures || 0} · 剩余 ${metrics.remaining === null || metrics.remaining === undefined ? "未设置" : metrics.remaining}`));
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

  const queueCard = dom("div", "card");
  queueCard.append(dom("h3", "", "Scamalytics 待处理队列"));
  const queue = Array.isArray(globalTask.quality_queue) ? globalTask.quality_queue : [];
  const [queueTable, queueBody] = table(["IP", "状态", "尝试次数", "下次重试", "错误"]);
  for (const item of queue) {
    const row = dom("tr");
    row.append(cell(item.ip), cell(item.status), cell(item.attempts), cell(formatTimestamp(item.next_attempt_at)), cell(item.last_error));
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
}

async function showGlobalLogs() {
  currentInstanceId = null;
  activateTab("tabGlobalLogs");
  try {
    const data = await api("global/logs");
    const security = data.security || {};
    const securityCard = dom("div", "card");
    securityCard.append(dom("h2", "", "日志与安全"));
    securityCard.append(dom("div", "muted", `存储后端：${security.storage_backend || "-"} · 敏感配置分离存储：${security.secret_storage_separate ? "是" : "否"} · Scamalytics 密钥：${security.api_key_configured ? "已配置" : "未配置"}`));
    securityCard.append(dom("div", "muted", `JSON 日志保留 ${security.log_retention_days || "-"} 天 · 文本日志轮转 ${security.text_log_backup_count || "-"} 份 · 备份目录 ${security.backup_directory || "-"}`));
    const history = Array.isArray(data.global_history) ? data.global_history : [];
    const [historyTable, historyBody] = table(["时间", "状态", "原因", "详情"]);
    for (const item of history.slice().reverse()) {
      const row = dom("tr");
      row.append(cell(formatTimestamp(item.at || item.created_at)), cell(item.status), cell(item.reason), cell(item.error_code || item.node_count));
      historyBody.append(row);
    }
    if (!history.length) { const row = dom("tr"); const empty = dom("td", "empty-state", "暂无全局任务日志。"); empty.colSpan = 4; row.append(empty); historyBody.append(row); }
    securityCard.append(dom("h3", "", "全局任务日志"), historyTable);
    el("content").replaceChildren(securityCard);
  } catch (error) {
    showError(error.message);
  }
}

function formatTimestamp(value) {
  if (!value) return "未计划";
  const date = new Date(Number(value) * 1000);
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
  summary.append(heading, dom("div", "muted", resourceSummary(instance)), toolbar);

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
    await operation();
    setOperation("操作完成", "ok");
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

async function saveGlobalSettings(button) {
  const payload = {
    vpn_gate_enabled: Boolean(el("globalVpnGateEnabled")?.checked),
    vpn_gate_schedule_time: el("globalVpnGateSchedule")?.value || "03:30",
    vpn_gate_timezone: el("globalVpnGateTimezone")?.value || "local",
    old_snapshot_grace_hours: Number(el("globalOldSnapshotGraceHours")?.value || 48),
    scamalytics_enabled: Boolean(el("globalScamalyticsEnabled")?.checked),
    scamalytics_username: el("globalScamalyticsUsername")?.value || "",
    scamalytics_daily_quota: Number(el("globalScamalyticsDailyQuota")?.value || 1000),
    scamalytics_rate_limit_per_minute: Number(el("globalScamalyticsRateLimit")?.value || 30),
    scamalytics_cache_ttl_days: Number(el("globalScamalyticsCacheDays")?.value || 7),
  };
  const apiKey = el("globalScamalyticsKey")?.value || "";
  if (apiKey) payload["scamalytics_api_key"] = apiKey;
  await runOperation(button, "正在保存质量配置…", async () => {
    await api("global/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await load();
  });
}

async function testGlobalScamalytics(button) {
  await runOperation(button, "正在测试质量配置…", async () => {
    await api("global/scamalytics/test", { method: "POST" });
  });
}

let pendingGlobalBackup = null;

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
    setOperation(`预检完成：${preview.change_count || 0} 项变更，请确认后恢复`, preview.changed ? "loading" : "ok");
  });
}

async function restoreGlobalBackup(button) {
  await runOperation(button, "正在恢复配置…", async () => {
    if (!pendingGlobalBackup) pendingGlobalBackup = await readGlobalBackup();
    if (!confirm("恢复前端配置会先自动备份当前配置，确定继续吗？")) return;
    await api("global/backup/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup: pendingGlobalBackup, confirmed: true }),
    });
    pendingGlobalBackup = null;
    await load();
  });
}

async function createInstance(button) {
  const select = el("catalogCountry");
  if (!select || !select.value) return;
  const item = instanceCatalog.find(entry => entry.country === select.value);
  if (!item) return;
  await runOperation(button, `正在创建 ${item.country}…`, async () => {
    await api("instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country: item.country, id: item.id }),
    });
    await load();
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
  try {
    const data = await api(`instances/${encodeURIComponent(instanceId)}/logs`);
    const card = dom("div", "card");
    card.append(dom("h3", "", "日志"));
    const lines = Array.isArray(data.logs) ? data.logs : [];
    const text = lines.map(item => `[${item.timestamp || ""}] ${item.level || ""} ${item.module || ""}: ${item.message || ""}`).join("\n");
    card.append(dom("pre", "", text || "暂无日志。"));
    el("content").append(card);
  } catch (error) {
    showError(error.message);
  }
}

document.addEventListener("change", event => {
  if (event.target.id === "catalogCountry") updateCatalogResources();
});

document.addEventListener("click", event => {
  const button = event.target.closest("button[data-console-action]");
  if (!button) return;
  const action = button.dataset.consoleAction;
  const instanceId = button.dataset.instanceId || "";
  const nodeId = button.dataset.nodeId || "";
  if (action === "overview") showOverview();
  else if (action === "global-nodes") showGlobalNodes();
  else if (action === "global-tasks") showGlobalTasks();
  else if (action === "global-logs") showGlobalLogs();
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
    mutateInstance(button, `instances/${encodeURIComponent(instanceId)}/service`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: button.dataset.serviceAction || "" }),
    });
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
