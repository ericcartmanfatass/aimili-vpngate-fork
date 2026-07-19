# AimiliVPN 🌐

Bilingual: [中文](#中文) | [English](#english)

---

<a name="中文"></a>
## 中文 (Chinese)

AimiliVPN 是一款基于官方 VPNGate 开放协议的高性能、零依赖 VPN 代理网关。它以纯 Python 标准库编写，内置美观响应式的管理网页，提供智能并发测速、多路由模式、出站代理网关、实时日志等强大功能。

本项目基于 `amilivpngate` 项目进行二次开发。

运行环境以 Linux 为准，最低支持 CPython 3.10，参考版本为 CPython 3.12；Ubuntu 22.04/24.04 与 Python 3.10/3.12 的组合由持续集成验证。开发与回归命令见 [TESTING.md](TESTING.md)。

v1.0.2 的全局节点调度、Scamalytics 配置和 Console 备份恢复实施记录见
[v1.0.2 全局 Console 实施说明](docs/v1.0.2-global-console.md)。

v1.0.3 的断线重试、离线前端、备份恢复安全闭环及存储/日志调整见
[v1.0.3 发布说明](docs/v1.0.3-release-notes.md)。

v1.0.2 中，VPNGate 节点由全局任务统一更新，实例只消费按国家筛选后的共享快照；
全局质量查询按 IP 去重、使用 7 天缓存并受每日配额限制。默认全局业务存储使用
SQLite，也可通过 `AIMILIVPN_GLOBAL_STORAGE_BACKEND=json` 临时回退到兼容 JSON。
Console 支持配置备份和完整业务数据备份，恢复前会预览变更并自动保留回滚快照。
Console 节点中心支持可用性、风险分数范围和数值风险排序；日志与安全页会展示最近备份/
恢复结果以及逐实例 SQLite/JSON 健康和迁移校验摘要。

---

### 🚀 一键极速部署 (支持 Debian/Ubuntu/CentOS/Alpine 等 Linux 系统)

在您的 Linux VPS 上以 root 用户执行以下对应命令：

#### 🌟 正式稳定版本（固定 Tag）
先到项目的 GitHub [Releases](https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases) 或 [Tags](https://github.com/ericcartmanfatass/aimili-vpngate-fork/tags) 页面查看版本号，例如 `v1.0.0`，
然后复制下面这一行执行；如果版本不同，只需要把命令中的 `v1.0.0` 换成实际版本号：

```bash
curl --fail --location "https://raw.githubusercontent.com/ericcartmanfatass/aimili-vpngate-fork/v1.0.0/install.sh" --output /tmp/aimilivpn-install.sh && sudo bash /tmp/aimilivpn-install.sh --ref v1.0.0
```

这一个命令会下载固定版本的安装器，由它自动安装依赖、检出代码、写入服务并启动 JP
实例。脚本还会校验下载的安装器与固定版本 checkout 中的 `install.sh` 完全一致。
不要从 `main` 下载，也不要使用 `curl | bash`。正式发布审计仍应使用
[带 SHA-256 的发布包流程](docs/installation.md)。

同一脚本还提供交互管理入口：

```bash
sudo bash /opt/aimilivpn/install.sh --menu
```

在菜单中选择安装/升级并填写新的固定 Tag 或完整 commit 时，已安装脚本会把控制权
交给该版本自己的安装器，再执行版本检出与一致性校验。

也可以直接使用 `--status`、`--web`、`--reset-password`、`--uninstall`；
非交互卸载必须额外添加 `--yes`，并默认保留源码和数据。
发布维护者还必须完成 [发布验收清单](docs/release-acceptance.md)，包括 Linux
CI、迁移/回滚演练和全新 Ubuntu 主机的安装至卸载验证。
> 💡 **安全提示**：管理网页默认只监听 `127.0.0.1`，安装日志不会输出完整安全路径。远程访问请先按 [TLS 反向代理指南](docs/reverse-proxy.md) 配置 Nginx/Caddy，再使用 `ml web` 主动查询入口。随机路径只能降低扫描噪声，不能替代密码和 HTTPS。

首次生成的随机密码不会写入日志，而是原子保存到 `0600` 的一次性凭据文件：Console 使用
`/etc/aimilivpn/console_initial_password`，实例 Web 使用各数据目录下的
`ui_initial_password`。读取后请立即修改密码；修改或执行 `sudo ml password reset` 会删除旧文件。

---

### 💡 快速使用指南 (小白必看)

部署成功后，如何使用它进行科学上网？

#### 第一步：登录 Web 管理后台
先按 [TLS 反向代理指南](docs/reverse-proxy.md) 配置 HTTPS，再运行 `ml web` 查询管理入口。临时维护可使用 SSH 端口转发，禁止把 `8787`/`8788` 明文端口直接开放到公网。

#### 第二步：获取并连接节点
1. 首次进入后台，节点列表可能正在进行首次自动测速与拉取。
2. 点击 **“更新节点”** 按钮（或通过网页下方的网关/日志进行状态检查），程序会在后台通过多线程并发测速，自动筛选出延迟最低、可连接的 VPNGate 节点。
3. 选择您喜欢的出站路由模式：
   - **智能自动配置**（推荐）：如果当前连接的节点失效，系统会在数秒内自动漂移连接至其他备用健康节点，无需手动干预。
   - **固定国家地区**：只选择指定国家（如日本 JP、韩国 KR、美国 US）的最佳节点。
   - **固定 IP 节点**：始终锁定连接到这一个特定节点。

#### 第三步：使用本机代理 (核心步骤)
为了防止代理端口暴露至公网被恶意扫描和滥用，AimiliVPN 的双效代理服务（默认端口 **`7928`**，自适应支持 SOCKS5 和 HTTP 协议）**默认仅绑定在本地回环地址（`127.0.0.1`）**，只接收 VPS 本机上的流量，不对外机提供代理。

* **🐍 Python 脚本中使用代理**:
  ```python
  import requests
  proxies = {
      "http": "http://127.0.0.1:7928",
      "https": "http://127.0.0.1:7928",
  }
  response = requests.get("https://www.google.com", proxies=proxies)
  ```
* **🐚 Shell 终端环境中使用代理**:
  在命令行执行以下命令，可以让当前终端的后续命令（如 `curl`、`wget` 等）走代理出口：
  ```bash
  export http_proxy="http://127.0.0.1:7928"
  export https_proxy="http://127.0.0.1:7928"
  ```
* **⚙️ 本地其他服务配置**:
  将本机的其他代理工具、爬虫框架或服务的出战代理设置为 `127.0.0.1:7928`。

> 💡 **安全提示**：代理端口不是管理网页的反向代理入口。不要将代理端口直接开放到公网。

---

### 🛠️ 核心功能与操作说明

* **合并操作面板**：将“更新节点”与“立即检测补齐”合并，一键触发多线程拉取与测速。
* **网关状态面板**：
  - **系统诊断**：检测网关心跳及后台各个子守护线程（网页服务、VPN连接管理、出站网关服务）是否正常运行。若有脚本未运行，会提示具体的异常原因。
  - **本地代理出口检测**：在网页端直接一键检测 VPS 后台对海外的实际连通状况，并回显真实的代理出站 IP 和所在地理位置。
* **日志追踪面板**：
  - **分类过滤**：可精准筛选查看特定功能的日志（如 VPN 连接日志、API 请求日志、系统异常等）。
  - **实时滚动与管理**：日志实时滚动加载，支持一键复制代码、一键导出 `.log` 日志文件到本地。
* **自定义地区与质量检测**：
  - 支持自定义地区规则，并可按地区筛选节点。
  - 节点质量结果会记录延迟、OpenVPN 检测状态、风险信息和最近检查时间。
  - 如配置 Scamalytics 账号，风险检测只在服务端执行，API key 不会下发到前端。
  - Console 设置页显示今日配额、缓存命中、实际请求、失败、延后和剩余量。
* **动态国家实例**：
  - 全新安装只启动 JP；VPNGate 首次刷新后，Console 会列出返回文件中当前有可用节点的其他国家。
  - 创建实例时由后端分配并持久化 TUN、策略路由表和端口，浏览器不能自行指定系统资源。

---

### ⚠️ 小白安装与运行常见问题 (FAQ)

#### 1. 提示 `Cannot allocate tun` 或 `Cannot open tun/tap dev`
* **原因**：VPS 宿主机未启用虚拟网卡（TUN/TAP 设备）。这种情况常见于 LXC 或 OpenVZ 架构的轻量 VPS。
* **解决办法**：请登录您的 VPS 服务商控制面板（如 SolusVM/Proxmox），找到 **Enable TUN/TAP** / **开启 TUN** 选项并启用，然后重启 VPS。如无此选项，请工单联系客服开启。

#### 2. 网页管理后台无法打开（链接超时或拒绝连接）
* **原因**：管理服务按设计只监听 loopback，不能通过 VPS 公网 IP 直接访问。
* **解决办法**：配置 [TLS 反向代理](docs/reverse-proxy.md)，公网只开放 HTTPS `443`；或使用 SSH 端口转发进行临时维护。不要开放 `8787`、`8788` 或 `7928`。

#### 3. 页面提示 `API Domain Blocked` 且备选节点显示为 0
* **原因**：您的 VPS DNS 解析异常，或者官方 VPNGate 域名遭防火墙拦截污染，导致无法下载节点列表。
* **解决办法**：
  * **设置上游代理**：如果您有其他可用的代理服务，可在网页管理面板中打开“管理员 -> 代理及网络设置”，配置有效的 HTTP/SOCKS5 上游代理，后台会自动通过该代理拉取更新。
  * **修复系统 DNS**：优先使用发行版支持的方式修改 DNS，例如 `resolvectl dns`、netplan、NetworkManager 或云厂商控制台。不要把直接编辑 `/etc/resolv.conf` 当作默认修复方式；它在很多 systemd-resolved 环境中只是临时文件或符号链接。

#### 4. VPN 已成功连接，但客户端设置代理后无法上网 (无流量)
* **原因**：部分系统启用了严格的反向路径过滤（`rp_filter`），导致策略路由的入站/出站数据包被系统误判丢弃。
* **解决办法**：重新运行固定版本安装脚本，或使用 `sudo bash /opt/aimilivpn/install.sh --menu` 选择安装/修复；安装器会将 `rp_filter` 设置为支持策略路由的宽松模式（值为 `2`）。

---

<a name="english"></a>
## English

AimiliVPN is a high-performance, zero-dependency VPN proxy gateway built entirely using Python's standard library. It parses official VPNGate servers, benchmarks latency, and routes traffic through a built-in dual-protocol (HTTP/SOCKS5) proxy server.

This project is a secondary development based on the `amilivpngate` project.

Linux is the supported runtime target. CPython 3.10 is the minimum supported version and CPython 3.12 is the reference version; CI verifies Ubuntu 22.04/24.04 with Python 3.10/3.12. See [TESTING.md](TESTING.md) for development and regression commands.

---

### 🚀 One-Click Installation

Run the corresponding command on your Linux VPS as root:

#### 🌟 Stable Release (immutable tag)
Find a version such as `v1.0.0` on the project's GitHub [Releases](https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases) or [Tags](https://github.com/ericcartmanfatass/aimili-vpngate-fork/tags)
page, then run this one-line command. Replace `v1.0.0` in both places if you
choose another version:

```bash
curl --fail --location "https://raw.githubusercontent.com/ericcartmanfatass/aimili-vpngate-fork/v1.0.0/install.sh" --output /tmp/aimilivpn-install.sh && sudo bash /tmp/aimilivpn-install.sh --ref v1.0.0
```

This command downloads the pinned installer, which installs dependencies,
checks out the matching source, configures services, and starts the JP
instance. The downloaded script must match the `install.sh` in the immutable
checkout. Never fetch it from `main` or use `curl | bash`. The checksummed
release archive remains the required path for formal release verification; see
[Verified installation and lifecycle operations](docs/installation.md).

The same installed script provides an interactive lifecycle menu:

```bash
sudo bash /opt/aimilivpn/install.sh --menu
```

When install/update is selected with a new immutable tag or full commit, the
installed entry hands control to that version's own installer before checkout
and consistency verification.

Direct actions include `--status`, `--web`, `--reset-password`, and
`--uninstall`; non-interactive uninstall additionally requires `--yes` and
preserves source and data by default.
Release maintainers must also complete the [release acceptance checklist](docs/release-acceptance.md),
including Linux CI, migration/rollback, and a clean Ubuntu install-through-uninstall drill.

> 💡 **Security note**: Management services bind to `127.0.0.1`, and install logs do not print the complete secret-path URL. Configure the [TLS reverse proxy](docs/reverse-proxy.md), then run `ml web` when you need the entry URL. The random path is scan-noise reduction, not authentication or encryption.

---

### 💡 Quick Start Guide

#### Step 1: Access the Web UI
Configure the [TLS reverse proxy](docs/reverse-proxy.md), then run `ml web` to retrieve the management entry. Use an SSH tunnel for temporary maintenance; never expose plaintext ports `8787` or `8788` publicly.

#### Step 2: Select Node and Mode
1. Wait for the program to complete its first automatic node speed benchmarks.
2. Under "Admin", you can trigger node fetching. The backend concurrently tests official VPNGate nodes and ranks them by latency.
3. Switch routes mode (Smart Auto, Specific Region, or Specific Server Node) according to your needs.

#### Managed country instances

A fresh install starts JP only. After VPNGate refreshes, the authenticated
Console lists other countries that currently have usable nodes. The backend—not
the browser—allocates and persists every TUN device, policy table, and port.

#### Step 3: Use Localhost Proxy (Core Step)
To prevent unauthorized scanning and abuse of the proxy port on the public internet, the built-in HTTP/SOCKS5 proxy server (default port **`7928`**) **binds to localhost (`127.0.0.1`) by default**. It is designed to route traffic generated locally on the VPS, rather than acting as a public proxy server.

* **🐍 Proxy in Python**:
  ```python
  import requests
  proxies = {
      "http": "http://127.0.0.1:7928",
      "https": "http://127.0.0.1:7928",
  }
  response = requests.get("https://www.google.com", proxies=proxies)
  ```
* **🐚 Proxy in Shell terminal**:
  ```bash
  export http_proxy="http://127.0.0.1:7928"
  export https_proxy="http://127.0.0.1:7928"
  ```
* **⚙️ Other local services**:
  Configure your scrapers, frameworks, or utility tools on this VPS to send traffic via `127.0.0.1:7928`.

> 💡 **Security note**: Do not expose the proxy port directly to the public internet.


---

### ⚠️ Common Troubleshooting (FAQ)

#### 1. Error: `Cannot allocate tun` or `Cannot open tun/tap dev`
* **Reason**: Virtual network adapter (TUN/TAP device) is disabled. This is common in OpenVZ/LXC VPS instances.
* **Solution**: Enable **TUN/TAP** in your VPS SolusVM/KiwiVM control panel, or submit a support ticket to your hosting provider.

#### 2. Cannot open the Web UI in the browser
* **Reason**: Management services intentionally listen on loopback and are not reachable through the VPS public IP.
* **Solution**: Configure the [TLS reverse proxy](docs/reverse-proxy.md) and expose only HTTPS port `443`, or use an SSH tunnel temporarily. Do not open ports `8787`, `8788`, or `7928` publicly.

#### 3. "API Domain Blocked" / Candidate nodes pool is empty (0 nodes)
* **Reason**: The official VPNGate domain is blocked or DNS resolution failed on your VPS.
* **Solution**: Add an HTTP/SOCKS5 upstream proxy in the settings panel (Admin -> Proxy Settings), or fix system DNS through your distribution-supported path such as `resolvectl dns`, netplan, NetworkManager, or your cloud provider console. Avoid treating direct edits to `/etc/resolv.conf` as the default fix because it is often managed by systemd-resolved.
