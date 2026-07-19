const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");

class FakeClassList {
  constructor(element) {
    this.element = element;
  }

  values() {
    return new Set(this.element.className.split(/\s+/).filter(Boolean));
  }

  add(...names) {
    const values = this.values();
    names.forEach(name => values.add(name));
    this.element.className = [...values].join(" ");
  }

  remove(...names) {
    const values = this.values();
    names.forEach(name => values.delete(name));
    this.element.className = [...values].join(" ");
  }
}

class FakeElement {
  constructor(tagName, text = "") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this._text = String(text);
    this.className = "";
    this.classList = new FakeClassList(this);
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this.value = "";
    this.disabled = false;
    this.scrollHeight = 0;
    this.clientHeight = 0;
    this.scrollTop = 0;
    this.listeners = {};
  }

  set textContent(value) {
    this._text = String(value ?? "");
    this.children = [];
  }

  get textContent() {
    return this._text + this.children.map(child => child.textContent).join("");
  }

  get innerText() {
    return this.textContent;
  }

  set innerHTML(_value) {
    throw new Error("security regression: innerHTML used by DOM-safe renderer");
  }

  append(...children) {
    for (const child of children) this.children.push(asNode(child));
  }

  prepend(...children) {
    this.children.unshift(...children.map(asNode));
  }

  replaceChildren(...children) {
    this._text = "";
    this.children = children.map(asNode);
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  addEventListener(name, callback) {
    if (!this.listeners[name]) this.listeners[name] = [];
    this.listeners[name].push(callback);
  }

  emit(name) {
    for (const callback of this.listeners[name] || []) callback({ target: this });
  }

  remove() {}
  select() {}
  click() {
    this.clicked = true;
    this.emit("click");
  }
}

function asNode(value) {
  return value instanceof FakeElement ? value : new FakeElement("#text", value);
}

class FakeDocument {
  constructor(ids = []) {
    this.elements = new Map(ids.map(id => [id, new FakeElement("div")]));
    this.body = new FakeElement("body");
    this.created = [];
  }

  createElement(tagName) {
    const element = new FakeElement(tagName);
    this.created.push(element);
    return element;
  }

  createTextNode(text) {
    return new FakeElement("#text", text);
  }

  getElementById(id) {
    if (!this.elements.has(id)) this.elements.set(id, new FakeElement("div"));
    return this.elements.get(id);
  }

  querySelectorAll(selector) {
    if (selector !== ".tab") return [];
    return [...this.elements.values()].filter(element => element.className.split(/\s+/).includes("tab"));
  }

  addEventListener() {}
  execCommand() { return true; }
}

function countTag(root, tagName) {
  const target = tagName.toUpperCase();
  return (root.tagName === target ? 1 : 0) + root.children.reduce((total, child) => total + countTag(child, tagName), 0);
}

function elementsByTag(root, tagName) {
  const target = tagName.toUpperCase();
  return [
    ...(root.tagName === target ? [root] : []),
    ...root.children.flatMap(child => elementsByTag(child, tagName)),
  ];
}

function source(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

test("malicious node id and status remain text in status DOM", () => {
  const ids = ["active_node_card", "total", "target", "active", "status", "proxy_status_badge", "proxy_ip_val", "proxy_latency_val", "btn_test_proxy"];
  const document = new FakeDocument(ids);
  const malicious = `<img src=x onerror="globalThis.pwned=true">`;
  const context = vm.createContext({
    document,
    state: { active_openvpn_node_id: malicious, last_check_message: malicious, proxy_ok: false, proxy_error: malicious },
    nodes: [{ id: malicious, active: true, country: malicious, ip: malicious, remote_port: 443 }],
    $: id => document.getElementById(id),
    translateCountry: value => value,
    translateIpType: value => value || "-",
    getLatencyClass: () => "latency-poor",
  });
  vm.runInContext(source("aimilivpn/web/static/app_render_status.js"), context);
  vm.runInContext("const activeNode = getActiveNodeForRender(); renderActiveNodeCard(activeNode); renderSummaryStatus(activeNode); renderProxyStatusCard();", context);

  assert.match(document.getElementById("active_node_card").textContent, /<img src=x/);
  assert.match(document.getElementById("status").textContent, /<img src=x/);
  assert.equal(countTag(document.getElementById("active_node_card"), "img"), 0);
  assert.equal(globalThis.pwned, undefined);
});

test("malicious log message remains text in log DOM", () => {
  const document = new FakeDocument(["log_filter_select", "log_terminal_container", "admin_dropdown", "logs_modal"]);
  document.getElementById("log_filter_select").value = "all";
  const malicious = `<svg onload="globalThis.pwned=true"></svg>`;
  const context = vm.createContext({ document, $: id => document.getElementById(id), fetch: async () => {}, console, setInterval, clearInterval, navigator: { clipboard: { writeText: async () => {} } }, alert() {} });
  vm.runInContext(source("aimilivpn/web/static/app_logs.js"), context);
  context.malicious = malicious;
  vm.runInContext("rawLogsCache = [{timestamp:'now', level:'ERROR', module:'VPN', message: malicious}]; filterAndRenderLogs();", context);

  const terminal = document.getElementById("log_terminal_container");
  assert.match(terminal.textContent, /<svg onload=/);
  assert.equal(countTag(terminal, "svg"), 0);
  assert.equal(globalThis.pwned, undefined);
});

test("malicious instance metadata remains text in Console DOM", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  const malicious = `<img src=x onerror="globalThis.pwned=true">`;
  const fetch = async url => {
    const payload = url.endsWith("instance-catalog")
      ? { catalog: [{ country: "DE", name: "Germany", id: "de", node_count: 4, creatable: true, installed: false, proxy_port: 7931, tun_dev: "tun13", policy_table: 113 }] }
      : { instances: [{ id: "jp", country: malicious, proxy_port: 7928, tun_dev: malicious, policy_table: 110, service_active: true, state: { last_check_message: malicious } }] };
    return { ok: true, status: 200, text: async () => JSON.stringify(payload) };
  };
  const context = vm.createContext({ document, fetch, console, location: { reload() {} }, confirm: () => false, prompt: () => "" });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await vm.runInContext("load()", context);

  const sidebar = document.getElementById("instances");
  const content = document.getElementById("content");
  assert.match(sidebar.textContent, /<img src=x/);
  assert.match(content.textContent, /<img src=x/);
  assert.equal(countTag(sidebar, "img"), 0);
  assert.equal(countTag(content, "img"), 0);
  assert.equal(globalThis.pwned, undefined);
});

test("Console global-node filters apply risk selection without HTML sinks", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs", "tabGlobalNodes"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  document.getElementById("tabGlobalNodes").className = "tab";
  const fetch = async () => ({ ok: true, status: 200, text: async () => JSON.stringify({ instances: [], catalog: [], settings: {}, task: {}, nodes: [] }) });
  class FakeOption extends FakeElement {
    constructor(text, value) {
      super("option", text);
      this.value = value;
    }
  }
  const context = vm.createContext({ document, fetch, console, location: { reload() {} }, confirm: () => false, prompt: () => "", Option: FakeOption });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await vm.runInContext(`
    globalTask = { snapshot_updated_at: 1 };
    globalNodes = [
      { server_ip: "203.0.113.10", country_short: "JP", latency_ms: 30, quality_result: { status: "ok", risk_score: 20, cache_expires_at: 9999999999 } },
      { server_ip: "203.0.113.20", country_short: "US", latency_ms: 40, quality_result: { status: "ok", risk_score: 90, cache_expires_at: 9999999999 } },
    ];
    showGlobalNodes();
  `, context);

  const content = document.getElementById("content");
  assert.match(content.textContent, /203\.0\.113\.10/);
  assert.match(content.textContent, /203\.0\.113\.20/);
  const selects = elementsByTag(content, "select");
  const riskSelect = selects[3];
  riskSelect.value = "high";
  riskSelect.emit("change");
  assert.doesNotMatch(content.textContent, /203\.0\.113\.10/);
  assert.match(content.textContent, /203\.0\.113\.20/);
  assert.equal(countTag(content, "img"), 0);
});

test("Console global-node availability, numeric risk and sort controls work together", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs", "tabGlobalNodes"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  class FakeOption extends FakeElement {
    constructor(text, value) {
      super("option", text);
      this.value = value;
    }
  }
  const context = vm.createContext({
    document,
    fetch: async () => ({ ok: true, status: 200, text: async () => "{}" }),
    console,
    location: { reload() {} },
    confirm: () => false,
    prompt: () => "",
    Option: FakeOption,
  });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await vm.runInContext(`
    globalNodes = [
      { server_ip: "203.0.113.10", active: true, latency_ms: 20, quality_result: { status: "ok", risk_score: 70 } },
      { server_ip: "203.0.113.20", probe_status: "available", latency_ms: 30, quality_result: { status: "ok", risk_score: 15 } },
      { server_ip: "203.0.113.30", probe_status: "unavailable", latency_ms: 40, quality_result: { status: "ok", risk_score: null } },
    ];
    showGlobalNodes();
  `, context);

  const content = document.getElementById("content");
  const selects = elementsByTag(content, "select");
  const inputs = elementsByTag(content, "input");
  selects[1].value = "available";
  selects[1].emit("change");
  assert.match(content.textContent, /203\.0\.113\.20/);
  assert.doesNotMatch(content.textContent, /203\.0\.113\.10|203\.0\.113\.30/);

  selects[1].value = "";
  selects[1].emit("change");
  inputs[1].value = "10";
  inputs[2].value = "80";
  inputs[1].emit("input");
  assert.match(content.textContent, /203\.0\.113\.10/);
  assert.match(content.textContent, /203\.0\.113\.20/);
  assert.doesNotMatch(content.textContent, /203\.0\.113\.30/);

  inputs[1].value = "";
  inputs[2].value = "";
  inputs[1].emit("input");
  selects[5].value = "risk";
  selects[5].emit("change");
  const rows = elementsByTag(content, "tr").map(row => row.textContent).filter(text => /203\.0\.113\./.test(text));
  assert.match(rows[0], /203\.0\.113\.20/);
  assert.match(rows[1], /203\.0\.113\.10/);
  assert.match(rows[2], /203\.0\.113\.30.*未检测/);
  for (const control of [...selects, ...inputs]) assert.ok(control.ariaLabel, `missing accessible name for ${control.tagName}`);
});

test("Console overview cards expose actionable presets", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  const context = vm.createContext({ document, fetch: async () => ({ ok: true, status: 200, text: async () => "{}" }), console, location: { reload() {} }, confirm: () => false, prompt: () => "" });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  vm.runInContext(`
    instanceList = [{ id: "jp", country: "JP", service_active: true, active_node: { ip: "203.0.113.1" }, state: {} }];
    globalNodes = [{ quality_result: { status: "ok", risk_score: 90 } }];
    globalTask = { quality_queue: [{ ip: "203.0.113.2" }] };
    showOverview();
  `, context);

  const buttons = elementsByTag(document.getElementById("content"), "button");
  assert.ok(buttons.some(button => button.dataset.consoleAction === "overview" && button.dataset.instanceFilter === "connected"));
  assert.ok(buttons.some(button => button.dataset.consoleAction === "global-nodes" && button.dataset.riskLevel === "high"));
  assert.ok(buttons.some(button => button.dataset.consoleAction === "global-tasks" && button.dataset.focusQueue === "true"));
});

test("Console lifecycle cancellation covers create, start, stop, restart and delete", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs", "catalogCountry"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  document.getElementById("catalogCountry").value = "JP";
  let fetchCalls = 0;
  const context = vm.createContext({
    document,
    fetch: async () => { fetchCalls += 1; return { ok: true, status: 200, text: async () => "{}" }; },
    console,
    location: { reload() {} },
    confirm: () => false,
    prompt: () => "",
  });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await new Promise(resolve => setImmediate(resolve));
  const baselineFetchCalls = fetchCalls;
  await vm.runInContext(`
    instanceCatalog = [{ id: "jp", country: "JP", proxy_port: 7928, tun_dev: "tun10", policy_table: 110 }];
    instanceList = [{ id: "jp", country: "JP", proxy_port: 7928, tun_dev: "tun10", policy_table: 110 }];
    createInstance({ disabled: false });
    serviceInstance("jp", "start", { disabled: false });
    serviceInstance("jp", "stop", { disabled: false });
    serviceInstance("jp", "restart", { disabled: false });
    deleteInstance("jp", { disabled: false });
  `, context);

  assert.equal(fetchCalls, baselineFetchCalls);
  assert.match(document.getElementById("operationStatus").textContent, /已取消/);
});

test("Console lifecycle confirmations send every approved mutation with safe deletion defaults", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs", "catalogCountry"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  document.getElementById("catalogCountry").value = "JP";
  const requests = [];
  const confirmationQueue = [true, true, true, true, true, false];
  const fetch = async (url, options = {}) => {
    requests.push({ url, options });
    let payload = {};
    if (url.endsWith("/instances")) payload = { instances: [{ id: "jp", country: "JP", proxy_port: 7928, tun_dev: "tun10", policy_table: 110 }] };
    else if (url.endsWith("instance-catalog")) payload = { catalog: [{ id: "jp", country: "JP", proxy_port: 7928, tun_dev: "tun10", policy_table: 110, node_count: 1 }] };
    else if (url.endsWith("global/settings")) payload = { settings: {} };
    else if (url.endsWith("global/tasks")) payload = { task: {} };
    else if (url.endsWith("global/nodes")) payload = { nodes: [] };
    return { ok: true, status: 200, text: async () => JSON.stringify(payload) };
  };
  const context = vm.createContext({
    document, fetch, console, location: { reload() {} },
    confirm: () => confirmationQueue.shift() ?? false,
    prompt: () => "jp",
  });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await new Promise(resolve => setImmediate(resolve));
  await vm.runInContext(`
    instanceCatalog = [{ id: "jp", country: "JP", proxy_port: 7928, tun_dev: "tun10", policy_table: 110 }];
    instanceList = [{ id: "jp", country: "JP", proxy_port: 7928, tun_dev: "tun10", policy_table: 110 }];
    createInstance({ disabled: false });
  `, context);
  await vm.runInContext(`serviceInstance("jp", "start", { disabled: false })`, context);
  await vm.runInContext(`serviceInstance("jp", "stop", { disabled: false })`, context);
  await vm.runInContext(`serviceInstance("jp", "restart", { disabled: false })`, context);
  await vm.runInContext(`deleteInstance("jp", { disabled: false })`, context);

  const mutations = requests.filter(request => request.options.method);
  assert.equal(mutations.filter(request => request.url.endsWith("/instances") && request.options.method === "POST").length, 1);
  const serviceActions = mutations
    .filter(request => request.url.endsWith("/instances/jp/service"))
    .map(request => JSON.parse(request.options.body).action);
  assert.deepEqual(serviceActions, ["start", "stop", "restart"]);
  const deletion = mutations.find(request => request.options.method === "DELETE");
  assert.ok(deletion);
  assert.deepEqual(JSON.parse(deletion.options.body), {
    confirmation: "jp",
    retain_data: true,
    purge_data_confirmation: "",
  });
});

test("Console permanent instance cleanup requires the strengthened purge confirmation", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  const requests = [];
  const prompts = ["jp", "purge:jp"];
  const context = vm.createContext({
    document,
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      return { ok: true, status: 200, text: async () => JSON.stringify(url.endsWith("/instances") ? { instances: [] } : {}) };
    },
    console,
    location: { reload() {} },
    confirm: () => true,
    prompt: () => prompts.shift() || "",
  });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await new Promise(resolve => setImmediate(resolve));
  await vm.runInContext(`deleteInstance("jp", { disabled: false })`, context);

  const deletion = requests.find(request => request.options.method === "DELETE");
  assert.ok(deletion);
  assert.deepEqual(JSON.parse(deletion.options.body), {
    confirmation: "jp",
    retain_data: false,
    purge_data_confirmation: "purge:jp",
  });
});

test("Console logs show backup, restore and per-instance migration status", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs", "tabGlobalLogs"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  class FakeOption extends FakeElement {
    constructor(text, value) {
      super("option", text);
      this.value = value;
    }
  }
  const payload = {
    global_history: [],
    instances: [{ id: "jp", country: "JP", logs: [{ timestamp: 1000, level: "INFO", message: "正常" }] }],
    security: {
      storage_backend: "sqlite",
      storage_health: { ok: true, quick_check: "ok" },
      latest_backup: { path: "/backup/config.json", updated_at: 1000, validated: true, checksum: "abc123" },
      last_restore: { at: 1100, ok: true, backup_before_restore: "/backup/pre.json", checksum: "def456" },
      instance_storage: [{ id: "jp", backend: "sqlite", ok: true, quick_check: "ok", migration: { backup_dir: "/backup/migration", total_count: 7, migrated_at: "2026-07-19T01:02:03Z", result: "success", documents: [{ kind: "nodes", checksum: "987xyz" }] } }],
    },
  };
  const context = vm.createContext({
    document,
    fetch: async () => ({ ok: true, status: 200, text: async () => JSON.stringify(payload) }),
    console,
    location: { reload() {} },
    confirm: () => false,
    prompt: () => "",
    Option: FakeOption,
    Intl,
  });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await new Promise(resolve => setImmediate(resolve));
  await vm.runInContext("showGlobalLogsV103('jp')", context);

  const content = document.getElementById("content");
  assert.match(content.textContent, /最近备份.*config\.json.*abc123/);
  assert.match(content.textContent, /最近恢复.*pre\.json.*def456/);
  assert.match(content.textContent, /实例存储与迁移.*migration.*987xyz/);
  assert.match(content.textContent, /迁移时间.*迁移结果.*成功/);
  const instanceSelect = elementsByTag(content, "select")[0];
  assert.equal(instanceSelect.value, "jp");
  assert.ok(instanceSelect.ariaLabel);
});

test("Console log filters re-redact exported content and use the versioned filename pattern", async () => {
  const ids = ["instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs", "tabGlobalLogs"];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  class FakeOption extends FakeElement {
    constructor(text, value) { super("option", text); this.value = value; }
  }
  class FakeBlob {
    constructor(parts, options) { this.parts = parts; this.options = options; }
  }
  const payload = {
    global_history: [
      { timestamp: 2000, level: "ERROR", module: "core", event: "connect", message: "password=super-secret token=abc123" },
      { timestamp: 1000, level: "INFO", module: "scheduler", event: "tick", message: "正常任务" },
    ],
    instances: [],
    security: { storage_backend: "sqlite", storage_health: { ok: true }, instance_storage: [] },
  };
  let exportedBlob = null;
  const context = vm.createContext({
    document,
    fetch: async () => ({ ok: true, status: 200, text: async () => JSON.stringify(payload) }),
    console,
    location: { reload() {} },
    confirm: () => false,
    prompt: () => "",
    Option: FakeOption,
    Intl,
    Blob: FakeBlob,
    URL: {
      createObjectURL(blob) { exportedBlob = blob; return "blob:test"; },
      revokeObjectURL() {},
    },
  });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await new Promise(resolve => setImmediate(resolve));
  await vm.runInContext("showGlobalLogsV103()", context);

  const content = document.getElementById("content");
  assert.doesNotMatch(content.textContent, /super-secret|abc123/);
  assert.match(content.textContent, /password=\[已脱敏\].*token=\[已脱敏\]/);
  const moduleInput = elementsByTag(content, "input")[0];
  moduleInput.value = "scheduler";
  moduleInput.emit("input");
  assert.doesNotMatch(content.textContent, /connect/);
  assert.match(content.textContent, /正常任务/);

  const exportButton = elementsByTag(content, "button").find(button => /导出筛选结果/.test(button.textContent));
  assert.ok(exportButton);
  exportButton.emit("click");
  assert.ok(exportedBlob);
  assert.doesNotMatch(exportedBlob.parts.join(""), /super-secret|abc123/);
  const anchor = document.created.filter(element => element.tagName === "A").at(-1);
  assert.ok(anchor.clicked);
  assert.match(anchor.download, /^aimilivpn-redacted-logs-\d{4}-\d{2}-\d{2}\.ndjson$/);
});

test("Console backup preview requires separate deletion confirmation and displays the restore report", async () => {
  const ids = [
    "instances", "instanceManager", "content", "tabOverview", "operationStatus", "instanceTabs",
    "globalBackupFile", "globalBackupPreview",
  ];
  const document = new FakeDocument(ids);
  document.getElementById("tabOverview").className = "tab active";
  document.getElementById("globalBackupFile").files = [{ text: async () => JSON.stringify({ schema_version: 1 }) }];
  const requests = [];
  const confirmations = [true, true];
  const fetch = async (url, options = {}) => {
    requests.push({ url, options });
    let payload = {};
    if (url.endsWith("backup/preview")) {
      payload = { preview: { changed: true, change_count: 2, added: [{ path: "instances.us" }], modified: [], removed: [{ path: "instances.jp" }], ignored: [], requires_deletion_confirmation: true } };
    } else if (url.endsWith("backup/restore")) {
      payload = { ok: true, backup_before_restore: "/backup/pre-restore.json", checksum: "sha256-report" };
    } else if (url.endsWith("/instances")) payload = { instances: [] };
    else if (url.endsWith("instance-catalog")) payload = { catalog: [] };
    else if (url.endsWith("global/settings")) payload = { settings: {} };
    else if (url.endsWith("global/tasks")) payload = { task: {} };
    else if (url.endsWith("global/nodes")) payload = { nodes: [] };
    return { ok: true, status: 200, text: async () => JSON.stringify(payload) };
  };
  const context = vm.createContext({
    document, fetch, console, location: { reload() {} },
    confirm: () => confirmations.shift() ?? false,
    prompt: () => "",
  });
  vm.runInContext(source("aimilivpn/web/static/console.js"), context);
  await new Promise(resolve => setImmediate(resolve));
  await vm.runInContext("previewGlobalBackup({ disabled: false, textContent: '预览恢复' })", context);

  assert.match(document.getElementById("globalBackupPreview").textContent, /新增（1）.*instances\.us.*删除（1）.*instances\.jp/s);
  await vm.runInContext("restoreGlobalBackup({ disabled: false, textContent: '确认恢复' })", context);
  const restoreRequest = requests.find(request => request.url.endsWith("backup/restore"));
  assert.ok(restoreRequest);
  const restoreBody = JSON.parse(restoreRequest.options.body);
  assert.equal(restoreBody.confirmed, true);
  assert.equal(restoreBody.confirm_deletions, true);
  assert.match(document.getElementById("operationStatus").textContent, /恢复报告：成功.*pre-restore\.json.*sha256-report/);
});
