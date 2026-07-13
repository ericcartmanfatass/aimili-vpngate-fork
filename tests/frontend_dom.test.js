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

  remove() {}
  select() {}
  click() {}
}

function asNode(value) {
  return value instanceof FakeElement ? value : new FakeElement("#text", value);
}

class FakeDocument {
  constructor(ids = []) {
    this.elements = new Map(ids.map(id => [id, new FakeElement("div")]));
    this.body = new FakeElement("body");
  }

  createElement(tagName) {
    return new FakeElement(tagName);
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
      ? { catalog: [{ country: "KR", id: "kr", installed: false, proxy_port: 7929, tun_dev: "tun11", policy_table: 111 }] }
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
