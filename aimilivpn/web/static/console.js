let instanceList = [];
let instanceCatalog = [];
let currentInstanceId = null;

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

async function api(path, options = {}) {
  const response = await fetch(`./api/${path}`, options);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (error) {
    throw new Error(`Invalid server response (${response.status})`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(typeof data.error === "string" ? data.error : `Request failed (${response.status})`);
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
  card.append(dom("b", "", "Operation failed"), dom("div", "", message || "Unknown error"));
  el("content").prepend(card);
  setOperation(message || "Operation failed", "bad");
}

function serviceStatus(instance) {
  return dom("span", instance.service_active ? "ok" : "bad", instance.service_active ? "running" : "stopped");
}

function resourceSummary(instance) {
  return `Proxy ${instance.proxy_port || "-"} · ${instance.tun_dev || "-"} · table ${instance.policy_table || "-"}`;
}

async function load() {
  setOperation("Loading instances...", "loading");
  const [instancesPayload, catalogPayload] = await Promise.all([
    api("instances"),
    api("instance-catalog"),
  ]);
  instanceList = Array.isArray(instancesPayload.instances) ? instancesPayload.instances : [];
  instanceCatalog = Array.isArray(catalogPayload.catalog) ? catalogPayload.catalog : [];
  renderSidebar();
  showOverview();
  setOperation("Ready", "ok");
}

function renderSidebar() {
  const container = el("instances");
  const cards = instanceList.map(instance => {
    const card = dom("div", "card");
    const heading = dom("div", "row");
    heading.append(dom("b", "", instance.country || "-"), dom("span", "pill", instance.id || "-"));
    const actions = dom("div", "toolbar compact");
    actions.append(
      actionButton("Open", "open", { instanceId: instance.id }),
      actionButton("Restart", "service", { instanceId: instance.id, serviceAction: "restart" }),
    );
    card.append(heading, dom("div", "muted", resourceSummary(instance)), serviceStatus(instance), actions);
    return card;
  });
  container.replaceChildren(...cards);
  renderCatalogForm();
}

function renderCatalogForm() {
  const panel = el("instanceManager");
  const available = instanceCatalog.filter(item => !item.installed);
  const title = dom("h3", "", "Add verified instance");
  const hint = dom("p", "muted", "Only backend-verified JP/KR/US catalog entries can be created.");
  if (!available.length) {
    panel.replaceChildren(title, hint, dom("div", "empty-state", "All verified instances are installed."));
    return;
  }
  const select = dom("select");
  select.id = "catalogCountry";
  for (const item of available) {
    const option = dom("option", "", `${item.country} (${item.id})`);
    option.value = item.country;
    select.append(option);
  }
  const resources = dom("div", "muted");
  resources.id = "catalogResources";
  const create = actionButton("Create and start", "create", {}, "primary");
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

function showOverview() {
  currentInstanceId = null;
  document.querySelectorAll(".tab").forEach(tab => tab.classList.remove("active"));
  el("tabOverview").classList.add("active");
  const card = dom("div", "card");
  card.append(dom("h2", "", "Overview"));
  if (!instanceList.length) {
    card.append(dom("div", "empty-state", "No managed instances are installed."));
    el("content").replaceChildren(card);
    return;
  }
  const [instancesTable, body] = table(["Country", "Service", "Proxy", "TUN", "Active node", "Message", "Action"]);
  for (const instance of instanceList) {
    const row = dom("tr");
    const statusCell = dom("td");
    statusCell.append(serviceStatus(instance));
    const actionCell = dom("td");
    actionCell.append(actionButton("Manage", "open", { instanceId: instance.id }));
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

async function openInstance(instanceId) {
  currentInstanceId = instanceId;
  setOperation(`Loading ${instanceId}...`, "loading");
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
    actionButton("Refresh nodes", "backend", { instanceId, backendAction: "refresh_nodes" }, "primary"),
    actionButton("Test proxy", "backend", { instanceId, backendAction: "test_proxy" }),
    actionButton("Disconnect", "backend", { instanceId, backendAction: "disconnect" }),
    actionButton(instance.service_active ? "Stop service" : "Start service", "service", {
      instanceId,
      serviceAction: instance.service_active ? "stop" : "start",
    }),
    actionButton("Restart service", "service", { instanceId, serviceAction: "restart" }),
    actionButton("Logs", "logs", { instanceId }),
    actionButton("Delete", "delete", { instanceId }, "danger"),
  );
  summary.append(heading, dom("div", "muted", resourceSummary(instance)), toolbar);

  const nodeCard = dom("div", "card");
  const [nodesTable, body] = table(["Status", "IP", "Country", "Latency", "Quality", "Action"]);
  if (!nodes.length) {
    const row = dom("tr");
    const empty = dom("td", "empty-state", "No nodes available.");
    empty.colSpan = 6;
    row.append(empty);
    body.append(row);
  }
  for (const node of nodes) {
    const row = dom("tr");
    const actions = dom("td");
    actions.append(
      actionButton("Connect", "connect", { instanceId, nodeId: node.id }),
      actionButton("Test", "test-node", { instanceId, nodeId: node.id }),
    );
    row.append(
      cell(node.active ? "active" : node.probe_status),
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
  setOperation(`Viewing ${instanceId}`, "ok");
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
    setOperation("Operation completed", "ok");
  } catch (error) {
    showError(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

async function createInstance(button) {
  const select = el("catalogCountry");
  if (!select || !select.value) return;
  const item = instanceCatalog.find(entry => entry.country === select.value);
  if (!item) return;
  await runOperation(button, `Creating ${item.country}...`, async () => {
    await api("instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country: item.country, id: item.id }),
    });
    await load();
  });
}

async function deleteInstance(instanceId, button) {
  if (!confirm(`Stop and delete instance ${instanceId}? Data is retained by default.`)) return;
  const confirmation = prompt(`Type ${instanceId} to confirm deletion:`) || "";
  if (confirmation !== instanceId) {
    setOperation("Deletion cancelled: confirmation did not match", "bad");
    return;
  }
  const purgeData = confirm("Also permanently delete this instance's data? Choose Cancel to retain it.");
  let purgeConfirmation = "";
  if (purgeData) {
    purgeConfirmation = prompt(`Type purge:${instanceId} to permanently delete data:`) || "";
    if (purgeConfirmation !== `purge:${instanceId}`) {
      setOperation("Deletion cancelled: data purge confirmation did not match", "bad");
      return;
    }
  }
  await runOperation(button, `Deleting ${instanceId}...`, async () => {
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
  await runOperation(button, "Working...", async () => {
    await api(path, options);
    if (currentInstanceId) await openInstance(currentInstanceId);
    else await load();
  });
}

async function showLogs(instanceId) {
  try {
    const data = await api(`instances/${encodeURIComponent(instanceId)}/logs`);
    const card = dom("div", "card");
    card.append(dom("h3", "", "Logs"));
    const lines = Array.isArray(data.logs) ? data.logs : [];
    const text = lines.map(item => `[${item.timestamp || ""}] ${item.level || ""} ${item.module || ""}: ${item.message || ""}`).join("\n");
    card.append(dom("pre", "", text || "No logs available."));
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
  else if (action === "logout") logout();
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
