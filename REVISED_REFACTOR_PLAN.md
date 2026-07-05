# AimiliVPN 渐进式重构与功能实施计划

## 0. 结论摘要

本项目适合重构，但不适合一次性重写。

当前仓库由少量脚本组成，其中 `vpngate_manager.py` 承担了配置、节点抓取、OpenVPN 连接、Web 后端、HTML/CSS/JS、状态存储和后台任务等大量职责。这个结构可以继续运行，但已经不适合继续添加自定义地区、节点质量评分、Scamalytics 风险检测、完整 CLI 和更复杂的前端。

推荐策略是：

1. 先建立测试和安全基线。
2. 再把纯逻辑逐步抽到模块中。
3. 保留现有 JSON 数据文件作为过渡存储。
4. 等模块边界稳定后，再引入 SQLite。
5. Web 静态资源、API、CLI、安装脚本分别拆分，避免同时大改。

核心原则：

- 不做全量重写。
- 不破坏现有部署和运行方式。
- 每一步都能单独编译、测试、回滚。
- 先处理安全风险，再添加新功能。

---

## 1. 当前项目状态评估

### 1.1 当前文件规模

当前项目主要文件：

```text
vpngate_manager.py   # 主程序，约 5600 行
vpn_utils.py         # 网络诊断、IP 信息、辅助函数
proxy_server.py      # HTTP/SOCKS5 本地代理
console_server.py    # 多实例统一控制台
install.sh           # 安装、systemd、ml 命令生成
README.md
```

### 1.2 当前架构问题

主要问题：

- Web UI 直接以大段 HTML/CSS/JS 字符串嵌在 Python 文件中。
- Web API、核心业务逻辑、OpenVPN 进程控制、后台线程耦合在一起。
- 配置分散在环境变量、JSON 文件、安装脚本和全局变量中。
- 节点数据、状态数据、认证配置、黑名单和 IP 缓存都直接使用 JSON 文件。
- CLI 当前主要由 `install.sh` 内嵌生成，后续维护成本高。
- 安全逻辑分散，Web 登录密码和 Console 登录密码仍有明文存储路径。
- 远程 `.ovpn` 配置从 VPNGate 解码后会直接写入并交给 OpenVPN 使用。
- 安装脚本里存在强制更新、系统配置修改、systemd 单元权限较宽等高风险点。

### 1.3 当前已有能力

已有能力应尽量保留：

- VPNGate 节点抓取。
- 节点测速和可用性检测。
- OpenVPN 连接和自动切换。
- HTTP/SOCKS5 本地代理。
- 多实例部署。
- Web 管理后台。
- Console 统一管理后台。
- `ml` 命令的基础状态、日志、服务管理能力。
- JSON 状态文件兼容现有安装。

---

## 2. 重构目标

### 2.1 架构目标

最终希望形成以下边界：

```text
aimilivpn/
  __init__.py

  core/
    config.py
    models.py
    storage.py
    auth.py
    security.py
    nodes.py
    regions.py
    scoring.py
    openvpn.py
    routing.py
    proxy.py
    logging_utils.py

  providers/
    vpngate.py
    quality_base.py
    local_probe.py
    scamalytics.py
    ipapi.py

  web/
    server.py
    api.py
    auth.py
    templates/
      login.html
      index.html
      console_login.html
      console_index.html
    static/
      app.js
      style.css
      nodes.js
      regions.js
      quality.js
      settings.js
      console.js

  cli/
    main.py
    commands.py

  system/
    install.py
    systemd.py
    service.py

tests/
  test_auth.py
  test_config.py
  test_storage_json.py
  test_vpngate_parse.py
  test_ovpn_sanitizer.py
  test_regions.py
  test_quality_scoring.py
  test_cli_parser.py
```

### 2.2 功能目标

新增能力：

- 自定义地区配置，可通过 Web 和 CLI 管理。
- 节点质量检测，包括本地 TCP/OpenVPN 检测。
- 可选 Scamalytics 风险检测。
- 质量、风险、延迟、IP 类型信息在前端展示。
- 更完整的 `ml` CLI 工具箱。
- 更清晰的设置、日志和服务管理界面。

### 2.3 安全目标

必须达成：

- 不再存储明文 Web/Console 登录密码。
- session token 使用 `secrets` 生成。
- 密码校验使用 PBKDF2 或更安全方案。
- 比较敏感值使用 `hmac.compare_digest`。
- 远程 `.ovpn` 配置必须经过 allowlist sanitizer。
- 默认不使用 HTTP 或跳过 TLS 验证抓取节点。
- 第三方 API key 永远只保存在服务端。
- API、日志、UI 不暴露原始 `.ovpn` 配置和敏感信息。
- systemd 单元尽量最小权限运行。

---

## 3. 非目标

本计划不做以下事情，除非后续明确要求：

- 不从零重写整个 VPN 路由和 OpenVPN 管理逻辑。
- 不引入重型前端框架。
- 不让 CLI 简单调用 Web API；CLI 应复用 core 模块。
- 不让前端接触 Scamalytics 或其他第三方 API key。
- 不一次性把所有 JSON 迁移到 SQLite。
- 不直接信任远端 `.ovpn` 内容。
- 不默认开放代理端口到公网。
- 不静默修改系统 DNS、sysctl 或路由配置。

---

## 4. 总体实施策略

### 4.1 推荐顺序

```text
Phase 0: 基线检查和最小测试
Phase 1: 安全基线
Phase 2: 包结构和纯逻辑抽取
Phase 3: JSON 存储抽象层
Phase 4: VPNGate provider 抽取
Phase 5: OpenVPN、routing、proxy 边界整理
Phase 6: Web API 与静态资源拆分
Phase 7: 自定义地区
Phase 8: 节点质量检测框架
Phase 9: Scamalytics provider
Phase 10: CLI 工具箱
Phase 11: SQLite 持久化
Phase 12: 安装脚本和 systemd 硬化
Phase 13: 前端 UI 整理与体验优化
Phase 14: 文档、迁移说明和发布检查
```

### 4.2 每个阶段的通用验收

每个阶段完成后至少执行：

```bash
python -m py_compile vpngate_manager.py vpn_utils.py proxy_server.py console_server.py
python -m py_compile aimilivpn/**/*.py
pytest -q
```

如果尚未引入 `pytest`，可先使用：

```bash
python -m unittest discover -s tests
```

---

## 5. Phase 0：基线检查和最小测试

### 5.1 目标

在改结构前，建立最基本的回归保护。

### 5.2 任务

创建：

```text
tests/
```

添加测试：

- `vpn_utils.parse_proxy_endpoint`
- `vpn_utils.parse_remote`
- VPNGate CSV 解析函数
- JSON 读写工具
- password/session 工具，等 Phase 1 创建后补齐
- OVPN sanitizer，等 Phase 1 创建后补齐

### 5.3 注意事项

当前项目无外部依赖。第一步可选择：

- 使用标准库 `unittest`，保持零依赖。
- 或引入 `pytest`，让后续测试更清晰。

推荐使用 `pytest`，但不要一次性引入复杂测试工具链。

### 5.4 验收标准

- 当前 Python 文件编译通过。
- 至少有 5 到 10 个纯函数测试。
- 后续抽模块时能快速发现解析行为变化。

---

## 6. Phase 1：安全基线

### 6.1 目标

先修高风险问题，再扩大功能面。

### 6.2 创建认证模块

创建：

```text
aimilivpn/core/auth.py
```

实现：

```python
def generate_password(length: int = 24) -> str: ...
def generate_session_token() -> str: ...
def hash_password(password: str) -> str: ...
def verify_password(password: str, stored_hash: str) -> bool: ...
```

要求：

- 使用 `secrets`，不用 `random`。
- 使用 `hashlib.pbkdf2_hmac`。
- 使用随机 salt。
- 使用足够迭代次数，例如 260000 或更高。
- 使用 `hmac.compare_digest`。
- 支持识别旧明文配置并迁移为 hash。

建议 hash 格式：

```text
pbkdf2_sha256$260000$salt_hex$hash_hex
```

### 6.3 迁移 Web 登录配置

当前 `ui_auth.json` 兼容策略：

旧格式：

```json
{
  "username": "admin",
  "password": "plain-password"
}
```

新格式：

```json
{
  "username": "admin",
  "password_hash": "pbkdf2_sha256$...",
  "secret_path": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

迁移规则：

- 如果存在 `password` 且不存在 `password_hash`，启动时生成 hash。
- 成功写入 `password_hash` 后删除明文 `password`。
- 文件权限设置为 `0600`。
- API 返回状态只允许 `password_set: true/false`，不得返回 hash 或明文。

### 6.4 迁移 Console 登录配置

同样处理：

```text
/etc/aimilivpn/console_auth.json
```

要求：

- 不再保存明文 `password`。
- Console session 使用 `secrets.token_urlsafe`。
- 登录校验走统一 `core/auth.py`。

### 6.5 OpenVPN 配置 sanitizer

创建：

```text
aimilivpn/core/security.py
```

实现：

```python
class UnsafeOpenVPNConfig(ValueError): ...

def sanitize_ovpn_config(config_text: str) -> str: ...
def redact_sensitive_text(text: str) -> str: ...
```

默认拒绝高风险指令：

```text
script-security
up
down
route-up
route-pre-down
down-pre
plugin
learn-address
client-connect
client-disconnect
auth-user-pass-verify
tls-verify
iproute
setenv
```

允许证书和密钥块：

```text
<ca>
<cert>
<key>
<tls-auth>
<tls-crypt>
```

初始 allowlist 可包含：

```text
client
dev
proto
remote
resolv-retry
nobind
persist-key
persist-tun
cipher
data-ciphers
auth
verb
mute
remote-cert-tls
auth-user-pass
comp-lzo
compress
reneg-sec
verify-x509-name
tls-client
pull
redirect-gateway
route
dhcp-option
```

注意：

- sanitizer 不应过早拒绝所有未知指令，否则可能破坏 VPNGate 兼容性。
- 可以先设置严格模式和兼容模式。
- 默认运行严格模式。
- 如果发现兼容性问题，只允许经过明确审查后加入 allowlist。

### 6.6 禁用不安全抓取回退

当前抓取逻辑包含：

- HTTPS 验证。
- HTTPS 不验证。
- HTTP fallback。

调整为：

- 默认只使用 HTTPS 且验证证书。
- 如需不安全模式，必须显式设置：

```text
ALLOW_INSECURE_FETCH=1
```

并在日志中明确写入 warning。

### 6.7 日志脱敏

创建：

```text
aimilivpn/core/logging_utils.py
```

基础能力：

```python
def redact_secret(value: str) -> str: ...
def redact_log_message(message: str) -> str: ...
```

脱敏对象：

- API key
- session token
- password
- password_hash
- Proxy-Authorization
- `.ovpn` 私钥块
- `auth-user-pass` 文件内容

### 6.8 验收标准

- 新生成配置不含明文登录密码。
- 旧配置启动后可自动迁移。
- session token 使用 `secrets`。
- 远程 `.ovpn` 写入文件前会经过 sanitizer。
- 不安全抓取默认关闭。
- 测试覆盖 auth 和 sanitizer。

---

## 7. Phase 2：包结构和纯逻辑抽取

### 7.1 目标

引入 `aimilivpn/` 包，但不急于删除旧入口。

### 7.2 创建目录

```text
aimilivpn/
  __init__.py
  core/
    __init__.py
  providers/
    __init__.py
  web/
    __init__.py
  cli/
    __init__.py
  system/
    __init__.py
```

### 7.3 抽取配置

创建：

```text
aimilivpn/core/config.py
```

职责：

- 环境变量解析。
- 默认端口。
- 默认目录。
- OpenVPN 命令。
- provider 开关。
- Scamalytics API key。
- 日志目录。
- 数据目录。

建议模型：

```python
@dataclass
class AppConfig:
    data_dir: Path
    config_dir: Path
    nodes_file: Path
    state_file: Path
    auth_file: Path
    local_proxy_host: str
    local_proxy_port: int
    ui_host: str
    ui_port: int
    openvpn_cmd: str
    tun_dev: str
    policy_table: str
    allowed_countries: set[str]
    allow_insecure_fetch: bool
```

提供：

```python
def load_config() -> AppConfig: ...
def env_int(...) -> int: ...
```

### 7.4 抽取模型

创建：

```text
aimilivpn/core/models.py
```

模型：

```python
@dataclass
class VpnNode:
    id: str
    source: str
    country: str | None
    country_code: str | None
    ip: str | None
    port: int | None
    proto: str | None
    hostname: str | None = None
    operator: str | None = None
    raw_score: int | None = None
    latency_ms: int | None = None
    probe_status: str = "not_checked"
    ip_type: str | None = None
    quality: str | None = None
    tags: list[str] = field(default_factory=list)
    last_seen_at: str | None = None
    config_text: str | None = None
```

```python
@dataclass
class RegionProfile:
    id: str
    name: str
    country_codes: list[str]
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    min_quality_score: int | None = None
    max_risk_score: int | None = None
    enabled: bool = True
```

```python
@dataclass
class QualityResult:
    node_id: str | None
    exit_ip: str | None
    tcp_latency_ms: int | None
    openvpn_success: bool | None
    handshake_ms: int | None
    risk_provider: str | None
    risk_score: int | None
    risk_level: str | None
    proxy_detected: bool | None
    datacenter_detected: bool | None
    country_match: bool | None
    checked_at: str
    raw_response: dict[str, Any] | None = None
```

### 7.5 兼容 dict

由于现有代码大量使用 dict，第一阶段不要强制全仓库改成 dataclass。

提供转换函数：

```python
def node_from_dict(data: dict[str, Any]) -> VpnNode: ...
def node_to_dict(node: VpnNode) -> dict[str, Any]: ...
```

### 7.6 验收标准

- 新包可导入。
- 旧 `vpngate_manager.py` 仍可运行。
- 配置和模型测试通过。
- 没有循环导入。

---

## 8. Phase 3：JSON 存储抽象层

### 8.1 目标

先抽象存储接口，暂时继续使用 JSON，避免一次性迁 SQLite。

### 8.2 创建

```text
aimilivpn/core/storage.py
```

### 8.3 Repository 接口

```python
class NodeRepository:
    def list_nodes(self, filters: NodeFilters | None = None) -> list[VpnNode]: ...
    def get(self, node_id: str) -> VpnNode | None: ...
    def upsert_many(self, nodes: list[VpnNode]) -> None: ...
    def update_node(self, node_id: str, patch: dict[str, Any]) -> None: ...
```

```python
class RegionRepository:
    def list_regions(self) -> list[RegionProfile]: ...
    def get(self, region_id: str) -> RegionProfile | None: ...
    def create(self, region: RegionProfile) -> None: ...
    def update(self, region_id: str, patch: dict[str, Any]) -> None: ...
    def delete(self, region_id: str) -> None: ...
```

```python
class QualityRepository:
    def save(self, result: QualityResult) -> None: ...
    def latest_for_node(self, node_id: str) -> QualityResult | None: ...
    def list_latest(self) -> dict[str, QualityResult]: ...
```

```python
class SettingsRepository:
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
```

### 8.4 JSON 文件布局

继续兼容现有：

```text
nodes.json
state.json
ui_auth.json
blacklist.json
ip_cache.json
```

新增：

```text
regions.json
quality_results.json
settings.json
operation_logs.jsonl
```

### 8.5 原子写入

JSON 写入要求：

- 写入临时文件。
- `replace` 原子替换。
- 文件权限尽量设置为 `0600`。
- 所有写入通过 repository，不再在业务代码里散落 `write_json`。

### 8.6 验收标准

- 原有 JSON 文件仍可读取。
- 新 repository 测试通过。
- 至少 `read_nodes`、`write nodes` 路径开始接入 repository。

---

## 9. Phase 4：VPNGate provider 抽取

### 9.1 目标

把节点抓取和解析从 `vpngate_manager.py` 移到 provider。

### 9.2 创建

```text
aimilivpn/providers/vpngate.py
```

职责：

- HTTPS 抓取 VPNGate CSV。
- 解析 CSV。
- Base64 解码 OpenVPN 配置。
- 调用 sanitizer。
- 生成 `VpnNode`。
- 支持 upstream HTTP/SOCKS proxy。

### 9.3 接口

```python
def fetch_vpngate_text(config: AppConfig) -> str: ...
def parse_vpngate_rows(text: str) -> list[dict[str, str]]: ...
def decode_config(encoded: str) -> str: ...
def row_to_node(row: dict[str, str], config_text: str) -> VpnNode: ...
def fetch_candidates(config: AppConfig) -> list[VpnNode]: ...
```

### 9.4 迁移策略

先从 `vpngate_manager.py` 调用新 provider。

不要同时改：

- 自动连接策略。
- OpenVPN 测试逻辑。
- Web API。

### 9.5 验收标准

- 解析测试通过。
- fetch 行为默认 HTTPS 验证。
- 不安全 fallback 必须由环境变量开启。
- `vpngate_manager.py` 中相关代码减少。

---

## 10. Phase 5：OpenVPN、routing、proxy 边界整理

### 10.1 目标

把系统层操作集中，降低 Web/API 和底层进程控制耦合。

### 10.2 OpenVPN 模块

创建：

```text
aimilivpn/core/openvpn.py
```

职责：

- 生成 OpenVPN 命令。
- 写入 sanitized 配置。
- 启动 OpenVPN。
- 读取日志直到 ready。
- 停止进程。
- 诊断错误。

接口：

```python
def split_openvpn_command(command: str) -> list[str]: ...
def openvpn_command(config: AppConfig, config_file: Path, route_nopull: bool, dev: str) -> list[str]: ...
def write_ovpn_config(path: Path, config_text: str) -> None: ...
def run_until_ready(...) -> OpenVPNRunResult: ...
def stop_process(process: subprocess.Popen[str] | None) -> None: ...
```

### 10.3 routing 模块

创建：

```text
aimilivpn/core/routing.py
```

职责：

- policy routing 设置。
- policy routing 清理。
- rp_filter 调整。
- 权限错误诊断。

注意：

- 不应在普通诊断中静默修改系统设置。
- 可保留当前运行逻辑，但要把修改动作集中。
- 后续安装脚本可以写入 `/etc/sysctl.d/aimilivpn.conf`。

### 10.4 proxy helper 模块

创建：

```text
aimilivpn/core/proxy.py
```

职责：

- proxy 配置读取。
- proxy 健康检查。
- upstream proxy 配置解析。

`proxy_server.py` 可先保留原文件，后续再迁到包内。

### 10.5 验收标准

- 旧的连接、断开、测试节点行为保持不变。
- OpenVPN 配置写入统一经过 `write_ovpn_config`。
- 路由相关系统操作集中到 `core/routing.py`。

---

## 11. Phase 6：Web API 与静态资源拆分

### 11.1 目标

把嵌入 Python 的前端资产移出源码。

### 11.2 目录

```text
aimilivpn/web/
  server.py
  api.py
  auth.py
  templates/
    login.html
    index.html
    console_login.html
    console_index.html
  static/
    app.js
    style.css
    nodes.js
    regions.js
    quality.js
    settings.js
    console.js
```

### 11.3 迁移策略

分两步：

1. 先只移动模板和静态文件，Python 仍使用原 Handler。
2. 再把 API routing 拆到 `web/api.py`。

### 11.4 API 兼容

保留当前 API：

```http
GET  /
GET  /api/state
GET  /api/nodes
GET  /api/config/{node_id}
GET  /api/gateway_status
GET  /api/logs
POST /api/login
POST /api/logout
POST /api/check
POST /api/refresh_nodes
POST /api/test_nodes
POST /api/test_node
POST /api/connect
POST /api/disconnect
POST /api/test_proxy
POST /api/update_credentials
POST /api/update_settings
POST /api/update_routing
POST /api/toggle_favorite
```

新增 API 使用更标准命名，但初期不要删除旧 API：

```http
GET    /api/status
GET    /api/nodes
POST   /api/nodes/refresh
POST   /api/nodes/test
POST   /api/nodes/connect
POST   /api/nodes/disconnect
GET    /api/settings
PUT    /api/settings
GET    /api/logs
```

旧 API 可以包装新 API。

### 11.5 静态文件服务

要求：

- 限制静态目录路径穿越。
- 设置正确 Content-Type。
- 对 HTML/API 使用 `Cache-Control: no-store`。
- 不在静态 JS 中写入敏感值。

### 11.6 验收标准

- 页面视觉和行为基本不变。
- Web UI 不再以大字符串嵌在 Python 源文件里。
- 原 API 仍可被旧前端调用。
- 新 API 初步可用。

---

## 12. Phase 7：自定义地区

### 12.1 目标

支持用户自定义地区规则，并从 Web/CLI 管理。

### 12.2 创建

```text
aimilivpn/core/regions.py
```

### 12.3 RegionProfile

```json
{
  "id": "asia-low-risk",
  "name": "Asia Low Risk",
  "country_codes": ["JP", "KR", "SG", "TW"],
  "include_keywords": ["Tokyo", "Seoul", "Singapore"],
  "exclude_keywords": ["Relay", "Academic"],
  "min_quality_score": 70,
  "max_risk_score": 40,
  "enabled": true
}
```

### 12.4 规则校验

要求：

- `id` 只允许小写字母、数字、短横线和下划线。
- `name` 非空。
- `country_codes` 统一转大写。
- `min_quality_score` 范围 0 到 100。
- `max_risk_score` 范围 0 到 100。
- include/exclude keyword 长度限制。

### 12.5 节点匹配

实现：

```python
def validate_region(region: RegionProfile) -> None: ...
def match_node(region: RegionProfile, node: VpnNode, quality: QualityResult | None = None) -> bool: ...
def preview_region(region: RegionProfile, nodes: list[VpnNode]) -> RegionPreview: ...
```

匹配字段：

- country_code
- country
- hostname
- operator
- location
- owner
- as_name
- quality score
- risk score

### 12.6 API

```http
GET    /api/regions
POST   /api/regions
GET    /api/regions/{id}
PUT    /api/regions/{id}
DELETE /api/regions/{id}
POST   /api/regions/{id}/preview
GET    /api/nodes?region=asia-low-risk
```

### 12.7 CLI

```bash
ml regions list
ml regions add asia-low-risk --name "Asia Low Risk" --country JP,KR,SG,TW --max-risk 40
ml regions edit asia-low-risk --min-quality 70
ml regions disable asia-low-risk
ml regions enable asia-low-risk
ml regions delete asia-low-risk
ml nodes list --region asia-low-risk
```

### 12.8 Web

添加 Regions 面板：

- 地区列表。
- 新增地区。
- 编辑地区。
- 删除地区。
- 启用/禁用。
- 预览匹配节点数量。

### 12.9 验收标准

- 地区可持久化。
- 重启后地区仍存在。
- Web 和 CLI 都能管理地区。
- 节点列表支持按地区过滤。
- 无效地区配置返回明确错误。

---

## 13. Phase 8：节点质量检测框架

### 13.1 目标

先建立 provider 接口，不直接把 Scamalytics 写进节点逻辑。

### 13.2 Provider 接口

创建：

```text
aimilivpn/providers/quality_base.py
```

```python
class QualityProvider(ABC):
    name: str

    @abstractmethod
    def check_ip(self, ip: str) -> QualityResult:
        ...
```

### 13.3 本地检测 provider

创建：

```text
aimilivpn/providers/local_probe.py
```

检测：

- TCP 是否可连。
- TCP 延迟。
- OpenVPN 是否握手成功。
- OpenVPN 握手耗时。
- 连接后的出口 IP。
- 出口国家是否匹配。

### 13.4 性能要求

必须避免过多 OpenVPN 进程：

- 先做 TCP preflight。
- TCP 不通的节点不跑 OpenVPN 测试。
- 限制并发 OpenVPN 测试。
- 对同一节点设置缓存 TTL。
- 对同一地区批量检测设置上限。

### 13.5 质量评分

创建：

```text
aimilivpn/core/scoring.py
```

示例规则：

```text
TCP reachable: +15
TCP latency < 100ms: +20
TCP latency 100-300ms: +10
OpenVPN success: +35
Handshake < 8s: +10
Risk score < 30: +20
Risk score 30-70: +10
Risk score > 70: -20
Country match: +10
Datacenter detected: -10
Proxy detected: -15
```

输出：

```python
@dataclass
class ScoreBreakdown:
    score: int
    label: str
    reasons: list[str]
```

标签：

```text
Excellent
Usable
Average
High Risk
Unknown
```

### 13.6 API

```http
GET  /api/quality?node_id=<node_id>
POST /api/quality/check-node
POST /api/quality/check-region
POST /api/quality/check-ip
```

### 13.7 CLI

```bash
ml quality check-node <node_id>
ml quality check-region <region_id>
ml quality check-ip <ip>
ml nodes list --sort quality
ml nodes list --max-risk 40
```

### 13.8 验收标准

- 不配置第三方 API key 时，本地质量检测可用。
- provider 失败不会影响 VPN 自动连接。
- quality result 被缓存。
- 前端能展示最新质量结果。

---

## 14. Phase 9：Scamalytics provider

### 14.1 目标

新增可选第三方风险检测。

### 14.2 创建

```text
aimilivpn/providers/scamalytics.py
```

### 14.3 配置

环境变量：

```text
SCAMALYTICS_USERNAME=
SCAMALYTICS_API_KEY=
SCAMALYTICS_TIMEOUT_SECONDS=8
SCAMALYTICS_CACHE_TTL_SECONDS=86400
SCAMALYTICS_RATE_LIMIT_PER_MINUTE=30
```

### 14.4 要求

- API key 只在服务端使用。
- API key 不返回给 Web。
- 设置 timeout。
- 设置 cache TTL。
- 设置 rate limit。
- 对 429 和 5xx 进行有限重试和 backoff。
- provider 失败只记录结果，不中断核心 VPN 功能。
- raw response 可存储，但 API/UI 默认不直接展示完整原文。

### 14.5 输出字段

```text
risk_score
risk_level
proxy_detected
datacenter_detected
raw_response
checked_at
provider_status
provider_error
```

### 14.6 Web 展示

显示：

- Risk score
- Risk level
- Provider
- Last checked
- API key configured/not configured

不得显示：

- API key 明文。
- 完整认证请求。
- 敏感 raw response 字段。

### 14.7 验收标准

- 未配置 API key 时 UI 显示未启用。
- 配置 API key 后可检测 IP 风险。
- 达到限流时返回可理解错误。
- 第三方服务失败不影响连接。

---

## 15. Phase 10：CLI 工具箱

### 15.1 目标

把 `ml` 从安装脚本内嵌逻辑迁移为项目内 CLI。

### 15.2 创建

```text
aimilivpn/cli/main.py
aimilivpn/cli/commands.py
```

### 15.3 命令结构

```bash
ml status

ml nodes list
ml nodes refresh
ml nodes test
ml nodes test --region jp
ml nodes connect <node_id>
ml nodes disconnect

ml regions list
ml regions add <id> --name <name> --country JP,KR
ml regions edit <id> --max-risk 40
ml regions enable <id>
ml regions disable <id>
ml regions delete <id>

ml quality check-node <node_id>
ml quality check-region <region_id>
ml quality check-ip <ip>

ml proxy status
ml proxy test
ml proxy restart
ml proxy set-port 7928

ml config show
ml config set <key> <value>

ml logs
ml logs --module vpn
ml logs --follow

ml service status
ml service start
ml service stop
ml service restart

ml console status
ml console restart

ml uninstall
```

### 15.4 实现要求

- 使用 `argparse`。
- CLI 直接调用 core 模块。
- 服务控制可调用 systemd helper。
- 输出保持脚本友好。
- 错误时返回非零 exit code。
- 对敏感值脱敏。

### 15.5 安装脚本过渡

`install.sh` 中 `/usr/bin/ml` 改为薄 wrapper：

```bash
#!/usr/bin/env bash
exec /usr/bin/python3 -m aimilivpn.cli.main "$@"
```

如果包路径还未安装，可临时：

```bash
cd /opt/aimilivpn
exec /usr/bin/python3 -m aimilivpn.cli.main "$@"
```

### 15.6 验收标准

- `ml status` 行为不退化。
- `ml jp logs` 等旧命令如果需要，提供兼容别名。
- 新 CLI 命令覆盖 Web 常用操作。
- CLI parser 有测试。

---

## 16. Phase 11：SQLite 持久化

### 16.1 目标

在 repository 接口稳定后，引入 SQLite。

### 16.2 数据库文件

```text
aimilivpn.db
```

默认路径：

```text
$VPNGATE_DATA_DIR/aimilivpn.db
```

### 16.3 表结构

```sql
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  country TEXT,
  country_code TEXT,
  ip TEXT,
  port INTEGER,
  proto TEXT,
  hostname TEXT,
  operator TEXT,
  raw_score INTEGER,
  latency_ms INTEGER,
  probe_status TEXT,
  ip_type TEXT,
  quality TEXT,
  ovpn_config_hash TEXT,
  last_seen_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS node_configs (
  node_id TEXT PRIMARY KEY,
  config_text TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS regions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  country_codes_json TEXT NOT NULL,
  include_keywords_json TEXT NOT NULL,
  exclude_keywords_json TEXT NOT NULL,
  min_quality_score INTEGER,
  max_risk_score INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS quality_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id TEXT,
  exit_ip TEXT,
  tcp_latency_ms INTEGER,
  openvpn_success INTEGER,
  handshake_ms INTEGER,
  risk_provider TEXT,
  risk_score INTEGER,
  risk_level TEXT,
  proxy_detected INTEGER,
  datacenter_detected INTEGER,
  country_match INTEGER,
  score INTEGER,
  label TEXT,
  raw_response_json TEXT,
  checked_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS operation_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json TEXT,
  created_at TEXT NOT NULL
);
```

### 16.4 迁移策略

提供：

```bash
ml storage migrate-json-to-sqlite
ml storage export-json
```

迁移流程：

1. 备份 JSON。
2. 创建 SQLite。
3. 导入 nodes、regions、quality、settings。
4. 验证数量。
5. 切换 backend。

### 16.5 配置

```text
STORAGE_BACKEND=json
STORAGE_BACKEND=sqlite
```

第一版默认仍可保持 JSON。

正式稳定后再切 SQLite 默认。

### 16.6 验收标准

- JSON backend 和 SQLite backend 测试共用同一接口测试。
- SQLite 可从旧 JSON 导入。
- 迁移失败不破坏旧 JSON。
- Web/CLI 不感知 backend 差异。

---

## 17. Phase 12：安装脚本和 systemd 硬化

### 17.1 目标

降低安装和系统集成风险。

### 17.2 安装源

修正：

- README 和 install.sh 默认仓库必须指向当前维护 fork。
- 避免拉取无关 upstream。
- 避免默认追踪不稳定 branch。
- 优先支持 release tag。

建议：

```bash
AIMILIVPN_VERSION=vX.Y.Z
```

或：

```bash
DEPLOY_BRANCH=main
```

但必须清晰提示。

### 17.3 避免强制覆盖

当前 `git reset --hard` 风险较高。

调整为：

- 默认 `git pull --ff-only`。
- 如果本地有修改，提示用户。
- 只有显式设置 `FORCE_UPDATE=1` 时才允许 reset。
- reset 前备份当前 commit 和 dirty diff。

### 17.4 systemd hardening

backend service 建议：

```ini
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/opt/aimilivpn /etc/aimilivpn /var/log/aimilivpn
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
```

如果 OpenVPN 仍必须 root，需要验证兼容性。

console service 建议更严格：

```ini
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/etc/aimilivpn /var/log/aimilivpn
CapabilityBoundingSet=
AmbientCapabilities=
```

### 17.5 DNS/sysctl 操作

要求：

- 不在运行时静默改 `/etc/resolv.conf`。
- 如果 DNS 异常，只提示诊断和修复命令。
- sysctl 写入集中到 `/etc/sysctl.d/aimilivpn.conf`。
- uninstall 时可移除该文件。

### 17.6 卸载

卸载必须：

- 明确列出将删除的 service。
- 默认保留数据。
- 删除数据必须二次确认。
- 删除源码必须二次确认。
- 清理 policy route。
- 清理 sysctl 文件。

### 17.7 验收标准

- 默认更新不会强制覆盖用户修改。
- systemd 单元更小权限。
- DNS/sysctl 修改行为可解释、可回滚。
- `/usr/bin/ml` 只是 wrapper。

---

## 18. Phase 13：前端 UI 整理与体验优化

### 18.1 目标

在 API 稳定后再做 UI 优化。

### 18.2 页面结构

```text
Dashboard
Nodes
Regions
Quality
Settings
Logs
Console
```

### 18.3 Dashboard

展示：

- 当前连接状态。
- 当前节点。
- 当前出口 IP。
- 代理状态。
- 节点总数。
- 可用节点数。
- 当前地区/路由模式。
- 最近一次质量检测时间。
- 后台线程健康状态。

### 18.4 Nodes

支持：

- 搜索。
- 国家筛选。
- 自定义地区筛选。
- IP 类型筛选。
- 质量排序。
- 风险排序。
- 延迟排序。
- 可用性筛选。
- 收藏。
- 连接。
- 单节点检测。
- 展开详情。

### 18.5 Regions

支持：

- 添加。
- 编辑。
- 删除。
- 启用/禁用。
- 规则预览。
- 匹配节点数量。

### 18.6 Quality

支持：

- Provider 状态。
- Scamalytics 是否配置。
- 最近检测结果。
- 批量检测。
- 错误展示。
- 缓存状态。

### 18.7 Settings

支持：

- Web 登录用户名。
- 修改密码。
- secret path。
- 代理端口。
- 路由模式。
- 日志级别。
- Provider 设置状态。
- 安全提示。

### 18.8 Logs

支持：

- 按模块筛选。
- 按级别筛选。
- 复制。
- 下载。
- 自动刷新。
- 脱敏展示。

### 18.9 UI 约束

- 不显示 API key 明文。
- 不显示密码/hash。
- 不显示原始 `.ovpn`。
- 错误信息要清楚，但不能泄露 secret。
- 页面应处理 loading、empty、error 状态。

### 18.10 验收标准

- 前端不再依赖 Python 内嵌字符串。
- UI 可管理地区和质量检测。
- 节点列表可按地区、质量、风险和延迟排序。
- 敏感值不会出现在页面源码或 API 响应中。

---

## 19. Phase 14：文档、迁移说明和发布检查

### 19.1 README 更新

说明：

- 新安装方式。
- 升级方式。
- 数据迁移。
- JSON/SQLite backend。
- Web 登录迁移。
- Scamalytics 配置。
- CLI 命令。
- 安全默认值。

### 19.2 MIGRATION 文档

创建：

```text
MIGRATION.md
```

内容：

- 从旧版本升级。
- 明文密码迁移。
- JSON 到 SQLite 迁移。
- `ml` wrapper 变化。
- systemd 单元变化。
- 如何回滚。

### 19.3 SECURITY 文档

创建：

```text
SECURITY.md
```

内容：

- 支持的安全策略。
- 默认监听地址。
- 代理公网开放风险。
- 第三方 API key 管理。
- `.ovpn` sanitizer 说明。

### 19.4 发布检查

发布前执行：

```bash
python -m py_compile vpngate_manager.py vpn_utils.py proxy_server.py console_server.py
python -m py_compile aimilivpn/**/*.py
pytest -q
```

可选：

```bash
ruff check .
bandit -r aimilivpn
shellcheck install.sh
```

### 19.5 验收标准

- 新用户可按 README 安装。
- 旧用户可按 MIGRATION 升级。
- 回滚路径明确。
- 发布版本不包含明文密钥或测试凭据。

---

## 20. 建议 PR / Commit 拆分

### Batch 1：测试和安全

```text
PR-01: Add baseline tests and package skeleton
PR-02: Add core/auth.py and migrate Web auth hash
PR-03: Migrate Console auth hash and secure sessions
PR-04: Add OpenVPN config sanitizer
PR-05: Disable insecure VPNGate fetch by default
```

### Batch 2：核心抽取

```text
PR-06: Add core/config.py and core/models.py
PR-07: Add JSON repository abstraction
PR-08: Extract providers/vpngate.py
PR-09: Extract core/openvpn.py
PR-10: Extract routing/proxy helpers
```

### Batch 3：Web 边界

```text
PR-11: Move main Web templates/static assets
PR-12: Move console templates/static assets
PR-13: Add web/api.py with compatibility routes
PR-14: Add new normalized /api/* endpoints
```

### Batch 4：自定义地区

```text
PR-15: Add RegionProfile model and JSON storage
PR-16: Add core/regions.py validation and matching
PR-17: Add /api/regions endpoints
PR-18: Add Regions UI
PR-19: Add regions CLI commands
```

### Batch 5：质量检测

```text
PR-20: Add quality provider interface
PR-21: Add local_probe provider
PR-22: Add quality result storage/cache
PR-23: Add scoring module
PR-24: Add Scamalytics provider
PR-25: Add Quality UI and CLI commands
```

### Batch 6：CLI

```text
PR-26: Add cli/main.py argparse entrypoint
PR-27: Add nodes/config/proxy/logs commands
PR-28: Replace install.sh embedded ml with wrapper
PR-29: Add backwards-compatible legacy ml aliases
```

### Batch 7：SQLite 和系统集成

```text
PR-30: Add SQLite backend behind storage interface
PR-31: Add JSON to SQLite migration command
PR-32: Harden systemd units
PR-33: Safer install/update/uninstall flow
```

### Batch 8：UI 和文档

```text
PR-34: Dashboard refresh
PR-35: Nodes table refresh
PR-36: Regions and Quality polish
PR-37: Settings and Logs polish
PR-38: README/MIGRATION/SECURITY updates
```

---

## 21. 风险清单

### 21.1 高风险

- OpenVPN sanitizer 过严导致部分 VPNGate 节点不可用。
- systemd 权限收紧导致 TUN、routing、SO_BINDTODEVICE 失败。
- JSON 到 SQLite 迁移导致旧数据读取异常。
- Web auth 迁移后用户无法登录。
- 安装脚本更新行为误删用户修改。

### 21.2 缓解措施

- sanitizer 加测试样本和兼容模式。
- systemd hardening 分阶段启用，先文档提示再默认开启。
- SQLite 迁移前自动备份 JSON。
- auth 迁移保留旧明文一次性校验路径，成功后删除明文。
- 安装更新默认不 reset，强制更新必须显式确认。

---

## 22. 最小可交付路线

如果希望尽快得到可见收益，推荐先做这条路线：

```text
1. 测试目录和 py_compile 检查
2. core/auth.py
3. core/security.py OVPN sanitizer
4. providers/vpngate.py
5. web/templates + web/static 拆分
6. core/regions.py + regions.json
7. /api/regions + Regions UI
8. cli/main.py + ml wrapper
```

这条路线完成后，项目会明显更安全、更可维护，并且已经具备添加质量检测和 Scamalytics 的基础。

---

## 23. 最终验收标准

完整计划完成后，应满足：

- 主业务逻辑不再集中在单个 5000+ 行文件中。
- Web UI 不再嵌在 Python 字符串中。
- Web、CLI、后台任务复用同一套 core 模块。
- Web/Console 登录不保存明文密码。
- 远端 `.ovpn` 配置经过 sanitizer。
- 自定义地区可从 Web 和 CLI 管理。
- 节点质量和风险结果可缓存、展示、排序。
- Scamalytics 可选启用，失败不影响核心 VPN 功能。
- CLI 覆盖常用管理操作。
- 安装脚本更安全，systemd 权限更收敛。
- 有可运行的测试集和迁移文档。

