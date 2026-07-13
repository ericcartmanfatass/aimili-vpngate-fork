let logsPollInterval = null;
let rawLogsCache = [];

function openLogsModal() {
  $("admin_dropdown").style.display = "none";
  $("logs_modal").style.display = "flex";
  loadLogs();
  if (logsPollInterval) clearInterval(logsPollInterval);
  logsPollInterval = setInterval(loadLogs, 2500);
}

function closeLogsModal() {
  $("logs_modal").style.display = "none";
  if (logsPollInterval) {
    clearInterval(logsPollInterval);
    logsPollInterval = null;
  }
}

async function loadLogs() {
  try {
    const response = await fetch("./api/v1/logs?limit=200&sort=timestamp&order=asc");
    const data = await response.json();
    if (Array.isArray(data.logs)) {
      rawLogsCache = data.logs;
      filterAndRenderLogs();
    }
  } catch (error) {
    console.error("加载日志失败", error);
  }
}

function filteredLogs() {
  const filter = $("log_filter_select").value;
  if (filter === "proxy") return rawLogsCache.filter(log => log.module === "Proxy");
  if (filter === "vpn") return rawLogsCache.filter(log => log.module === "VPN");
  if (filter === "system") return rawLogsCache.filter(log => !["Proxy", "VPN"].includes(log.module));
  return rawLogsCache;
}

function logColor(log) {
  if (log.level === "ERROR") return "#f43f5e";
  if (log.level === "WARNING") return "#fbbf24";
  if (log.module === "Proxy") return "#38bdf8";
  if (log.module === "VPN") return "#34d399";
  return "#a5b4fc";
}

function filterAndRenderLogs() {
  const terminal = $("log_terminal_container");
  if (!terminal) return;
  const logs = filteredLogs();
  if (!logs.length) {
    const empty = document.createElement("div");
    empty.className = "log-empty-state";
    empty.textContent = "暂无该类型日志。";
    terminal.replaceChildren(empty);
    return;
  }

  const atBottom = terminal.scrollHeight - terminal.clientHeight <= terminal.scrollTop + 50;
  const lines = logs.map(log => {
    const line = document.createElement("div");
    line.className = "log-line";
    line.style.color = logColor(log);
    line.textContent = `[${log.timestamp || ""}] [${log.level || ""}] [${log.module || ""}] ${log.message || ""}`;
    return line;
  });
  terminal.replaceChildren(...lines);
  if (atBottom) terminal.scrollTop = terminal.scrollHeight;
}

function currentLogText() {
  const terminal = $("log_terminal_container");
  return terminal ? (terminal.innerText || terminal.textContent || "").trim() : "";
}

function copyLogContent() {
  const text = currentLogText();
  if (!text || text === "暂无该类型日志。") {
    alert("当前没有可复制的日志。");
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    alert("日志已复制到剪贴板。");
  }).catch(error => {
    console.error("复制失败", error);
    const field = document.createElement("textarea");
    field.value = text;
    document.body.appendChild(field);
    field.select();
    document.execCommand("copy");
    field.remove();
  });
}

function exportLogContent() {
  const text = currentLogText();
  if (!text || text === "暂无该类型日志。") {
    alert("当前没有可导出的日志。");
    return;
  }
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `vpngate_log_${$("log_filter_select").value}_${new Date().toISOString().slice(0, 10)}.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
