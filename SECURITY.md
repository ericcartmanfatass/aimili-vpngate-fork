# 安全说明

## 可信安装与生命周期边界

远程安装只支持固定项目仓库的不可变发布 Tag 或完整 commit。运行本地安装器前必须校验发布的
SHA-256，禁止把移动分支通过管道直接交给 Shell。详见
[`docs/installation.md`](docs/installation.md)。

发布候选还必须完成 [`docs/release-acceptance.md`](docs/release-acceptance.md) 定义的 Linux
矩阵、人工边界审查、迁移/回滚演练和一次性主机生命周期证据。缺少证据属于发布阻断项，
不能用 Windows 本地测试豁免。

全新 systemd 安装只创建 JP。其他国家只有在最新服务端 VPNGate 目录中存在可用节点，且请求
来自已认证 Console Session 时才能创建。后端分配并校验 TUN、策略路由表、端口、路径和服务
归属；实例环境文件、目录、来源元数据和审计元数据使用 `0600`。浏览器只能提交目录国家代码，
不能提交单元文件名、环境路径、TUN、策略表或端口。

后端单元的 capability 限于 `CAP_NET_ADMIN` 和 `CAP_NET_RAW`。Console 的 capability
bounding set 为空；受管路径之外严格只读，并启用私有临时目录、地址族/命名空间限制和禁止提权。

## 默认监听地址

Backend Web UI、统一 Console 和本地代理默认绑定到 `127.0.0.1`，避免直接对公网暴露。Web 的 IPv6 绑定失败时只允许回退到 IPv4 loopback，不得回退到 `0.0.0.0`。

管理面不支持公网明文 HTTP。远程管理必须使用同机 Nginx/Caddy 等 TLS 反向代理，具体配置见 [`docs/reverse-proxy.md`](docs/reverse-proxy.md)。不要在防火墙或云安全组中开放 backend/Console upstream 端口。

`X-Forwarded-*` 默认不受信任。只有显式启用 `AIMILIVPN_TRUST_PROXY_HEADERS=1` 且请求来自 `AIMILIVPN_TRUSTED_PROXY_ADDRESSES` 中的 loopback IP 时，`X-Forwarded-Proto: https` 才可使 Session Cookie 携带 `Secure`。非 loopback 的受信地址会被忽略。

## 登录凭据

Web 和 Console 登录密码应以 PBKDF2 hash 存储，不应保存明文 `password` 字段。配置文件权限应限制为 `0600`。

Session token 和随机密码由 Python `secrets` 生成。

随机 secret path 只用于降低无关扫描噪声，不是认证或传输安全措施。普通启动日志不应输出完整 secret-path URL；管理员可在需要时通过 `ml web` 主动查询。

首次访问 Console 时，安装和启动日志不会交付明文密码。自动生成的一次性初始凭据原子写入
`/etc/aimilivpn/console_initial_password`；实例 Web 凭据写入数据目录下的
`ui_initial_password`。文件权限必须为 `0600`，日志只允许提示路径。保存新密码或执行
`sudo ml password reset` 会删除旧的一次性文件；重置后的新密码只在当前交互终端显示一次，
服务端认证配置始终只保存哈希。

## OpenVPN 配置

从 VPNGate 获取的 `.ovpn` 内容被视为不可信输入。写入磁盘前应经过 sanitizer，拒绝高风险指令，例如脚本钩子、plugin 和验证回调类配置。

API、日志和 UI 不应展示原始 `.ovpn` 内容或私钥块。

## 第三方 API key

Scamalytics 等第三方 API key 只能保存在服务端的独立私有 secrets 文件
（`global_secrets.json`）或受控环境变量中，不能写入全局 SQLite、普通设置文件、日志、
前端响应或备份。前端 API 只返回是否已配置和掩码；用户名可作为配置项显示，但不得与
API key 一起作为秘密下发。保存新 key 时沿用旧 key，除非管理员明确提交新值。

v1.0.3 的全局配置文件和全局数据库应保持 `0600`。完整业务备份只允许包含节点元数据、
质量结果、黑名单、任务历史和非敏感设置；OpenVPN 正文、原始第三方响应、密码、Session、
令牌、API key 和系统资源分配字段必须被排除。JSON backend 只是兼容/回退路径，不改变上述
敏感字段边界。

## DNS 和系统参数

不要把直接编辑 `/etc/resolv.conf` 当作默认 DNS 修复方式。现代 Linux 上它通常由 systemd-resolved、NetworkManager 或 netplan 管理。

策略路由所需的 `rp_filter=2` 应通过 `/etc/sysctl.d/99-aimilivpn.conf` 持久配置，并在卸载或回滚时可审计、可移除。

## 代理公网风险

HTTP/SOCKS5 代理一旦绑定公网地址，就可能被扫描、滥用或用于转发恶意流量。默认应保持 localhost 绑定；公网开放必须配合访问控制。
