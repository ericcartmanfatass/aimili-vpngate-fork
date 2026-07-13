# Security Notes

## Trusted installation and lifecycle boundary

Remote installation is supported only from the fixed project repository and an
explicit immutable release tag or full commit. Verify the published SHA-256
before running the local installer; never pipe a moving branch into a shell.
See [`docs/installation.md`](docs/installation.md).

Release candidates also require the Linux matrix, manual boundary review,
migration/rollback drill, and disposable-host lifecycle evidence defined in
[`docs/release-acceptance.md`](docs/release-acceptance.md). Missing evidence is
a release blocker, not a warning that can be waived by a Windows test run.

A fresh systemd install creates JP only. Additional countries can be created
only when they appear with usable nodes in the latest server-side VPNGate
country catalog and the request comes from an authenticated Console session.
The backend allocates and validates all TUN, policy-table, port, path, and
service ownership values. Instance environment files, the catalog, source
metadata, and audit metadata use mode 0600. Browser input can provide only a
catalog country code; it can never provide a unit filename, environment path,
TUN device, policy table, or port.

The backend unit is capability-bounded to `CAP_NET_ADMIN` and `CAP_NET_RAW`.
The Console has an empty capability bounding set, a strict read-only filesystem
outside explicit managed paths, private temporary storage, restricted address
families/namespaces, and no privilege escalation.

## 默认监听地址

Backend Web UI、统一 Console 和本地代理默认绑定到 `127.0.0.1`，避免直接对公网暴露。Web 的 IPv6 绑定失败时只允许回退到 IPv4 loopback，不得回退到 `0.0.0.0`。

管理面不支持公网明文 HTTP。远程管理必须使用同机 Nginx/Caddy 等 TLS 反向代理，具体配置见 [`docs/reverse-proxy.md`](docs/reverse-proxy.md)。不要在防火墙或云安全组中开放 backend/Console upstream 端口。

`X-Forwarded-*` 默认不受信任。只有显式启用 `AIMILIVPN_TRUST_PROXY_HEADERS=1` 且请求来自 `AIMILIVPN_TRUSTED_PROXY_ADDRESSES` 中的 loopback IP 时，`X-Forwarded-Proto: https` 才可使 Session Cookie 携带 `Secure`。非 loopback 的受信地址会被忽略。

## 登录凭据

Web 和 Console 登录密码应以 PBKDF2 hash 存储，不应保存明文 `password` 字段。配置文件权限应限制为 `0600`。

Session token 和随机密码由 Python `secrets` 生成。

随机 secret path 只用于降低无关扫描噪声，不是认证或传输安全措施。普通启动日志不应输出完整 secret-path URL；管理员可在需要时通过 `ml web` 主动查询。

## OpenVPN 配置

从 VPNGate 获取的 `.ovpn` 内容被视为不可信输入。写入磁盘前应经过 sanitizer，拒绝高风险指令，例如脚本钩子、plugin 和验证回调类配置。

API、日志和 UI 不应展示原始 `.ovpn` 内容或私钥块。

## 第三方 API key

Scamalytics 等第三方 API key 只能保存在服务端环境变量或服务端配置中。前端 API 只允许返回“是否已配置”、timeout、cache TTL 和 rate limit 等状态，不得返回 key 或 username。

## DNS 和系统参数

不要把直接编辑 `/etc/resolv.conf` 当作默认 DNS 修复方式。现代 Linux 上它通常由 systemd-resolved、NetworkManager 或 netplan 管理。

策略路由所需的 `rp_filter=2` 应通过 `/etc/sysctl.d/99-aimilivpn.conf` 持久配置，并在卸载或回滚时可审计、可移除。

## 代理公网风险

HTTP/SOCKS5 代理一旦绑定公网地址，就可能被扫描、滥用或用于转发恶意流量。默认应保持 localhost 绑定；公网开放必须配合访问控制。
