# Security Notes

## 默认监听地址

Backend Web UI 和本地代理默认绑定到本机地址，避免直接对公网暴露。只有在明确设置 `LOCAL_PROXY_HOST="::"` 或类似公网监听地址时，代理才会对外开放。

如果必须开放公网访问，请至少配置防火墙或云安全组，只允许可信 IP 访问管理端口和代理端口。

## 登录凭据

Web 和 Console 登录密码应以 PBKDF2 hash 存储，不应保存明文 `password` 字段。配置文件权限应限制为 `0600`。

Session token 和随机密码由 Python `secrets` 生成。

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
