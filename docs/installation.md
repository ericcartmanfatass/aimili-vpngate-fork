# 安装、升级与实例生命周期

AimiliVPN 必须从固定仓库的不可变发布 Tag 或完整 commit 安装。全新 systemd 安装只创建并启动 JP 实例；其他国家/地区只有在最新 VPNGate 数据中存在可用节点后，才能由已登录管理员通过 Console 创建。

## 一键安装与日常管理

从项目 [Releases](https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases) 或 [Tags](https://github.com/ericcartmanfatass/aimili-vpngate-fork/tags) 页面确认版本。以下以 `v1.0.3` 为例：

```bash
curl --fail --location \
  "https://raw.githubusercontent.com/ericcartmanfatass/aimili-vpngate-fork/v1.0.3/install.sh" \
  --output /tmp/aimilivpn-install.sh
sudo bash /tmp/aimilivpn-install.sh --ref v1.0.3
```

安装器会安装依赖、检出指定 Tag/commit、比对安装器 SHA-256、配置 systemd，并启动初始 JP 实例。它不会选择移动分支或静默安装其他版本。

已有安装可继续使用同一脚本管理：

```bash
sudo bash /opt/aimilivpn/install.sh --menu
sudo bash /opt/aimilivpn/install.sh --status
sudo bash /opt/aimilivpn/install.sh --web
sudo bash /opt/aimilivpn/install.sh --reset-password
sudo bash /opt/aimilivpn/install.sh --uninstall --yes
```

升级时在菜单中选择安装/升级并输入新的不可变 Tag 或完整 commit。全新安装仍只创建 JP；其他实例必须从经过认证的服务端目录创建。卸载默认保留源码和数据，永久删除数据或源码必须使用 `ml uninstall` 的独立确认参数。

## 发布包校验

正式发布必须同时提供 `aimilivpn-VERSION.tar.gz` 和 `SHA256SUMS`。维护者从已审核的发布 Tag 执行：

```bash
bash scripts/build-release.sh v1.0.3
```

使用者下载后先校验再安装：

```bash
VERSION=v1.0.3
curl --fail --location --remote-name \
  "https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases/download/${VERSION}/aimilivpn-${VERSION}.tar.gz"
curl --fail --location --remote-name \
  "https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases/download/${VERSION}/SHA256SUMS"
grep " aimilivpn-${VERSION}.tar.gz$" SHA256SUMS | sha256sum --check --strict
tar -xzf "aimilivpn-${VERSION}.tar.gz"
cd "aimilivpn-${VERSION}"
sudo AIMILIVPN_REF="${VERSION}" bash install.sh
```

不要执行 `curl | bash`，也不要从 `main` 直接安装。远程部署只接受 `vX.Y.Z` Tag 或 40 位完整 commit。安装来源会以 `0600` 权限记录到 `/etc/aimilivpn/install-source.json`。`AIMILIVPN_LOCAL_DEV=1` 仅用于本地开发测试，会跳过正式发布来源校验。

## 初始 Console 与实例 Web 密码

服务首次生成认证配置时，明文密码不会写入认证 JSON，也不会打印到安装日志。一次性初始凭据会原子写入仅 root/服务账户可读的 `0600` 文件：

```text
/etc/aimilivpn/console_initial_password
/opt/aimilivpn/data/<实例>/ui_initial_password
```

启动日志只会提示文件路径，不会包含密码。管理员读取并保存凭据后应尽快修改密码；保存新密码时对应的一次性文件会被删除。也可以在交互式终端主动重置 Console 密码：

```bash
sudo ml password reset
```

该命令原子更新密码哈希、删除旧的一次性凭据文件、重启 Console，并只在当前终端显示新密码一次。`ml password` 只报告密码状态。使用 `ml web` 查询回环地址入口。

## v1.0.3 全局 Console 与数据

v1.0.3 由一个全局任务统一更新 VPNGate 节点并服务所有实例。全局节点、质量任务和历史默认写入 SQLite；受控回退时可在启动 Console 前设置：

```bash
export AIMILIVPN_GLOBAL_STORAGE_BACKEND=json
```

实例业务数据同样默认使用 SQLite；单实例兼容回退使用 `STORAGE_BACKEND=json`。OpenVPN 内容、锁和短生命周期状态仍保存在各实例受限目录中。

Console 提供配置备份和完整业务备份。恢复流程固定为：上传、格式/版本校验、差异预览、显式确认、恢复前自动快照、失败自动回滚。包含删除项时需要第二次独立确认。备份不会包含 systemd 单元、TUN、策略路由表、端口、OpenVPN 正文、密码、Session、Token 或 Scamalytics API Key；恢复后缺失的敏感凭据必须重新录入。

“日志与安全”页会显示最近备份路径、时间、校验结果与 SHA-256，最近一次恢复结果，以及每个实例的存储后端、健康状态、迁移备份目录、条数和校验摘要。页面时间按浏览器本地时区显示。

## 升级与回滚

使用新版本的已验证 Tag 重新运行安装器。默认升级在工作区脏或目标不是 fast-forward 时停止。`FORCE_UPDATE=1` 仅用于显式恢复；重置前会在 `/var/backups/aimilivpn/TIMESTAMP/` 写入 Git bundle、工作区补丁和状态文件。

生产升级前额外备份配置与数据：

```bash
sudo cp -a /etc/aimilivpn "/etc/aimilivpn.backup.$(date +%s)"
sudo cp -a /opt/aimilivpn/data "/opt/aimilivpn-data.backup.$(date +%s)"
```

回滚步骤：检出上一个已验证 Tag，恢复上述备份，执行 `systemctl daemon-reload`，再重启 Console 和保留实例。JSON/SQLite 的详细演练见 [`../MIGRATION.md`](../MIGRATION.md)。

## 实例生命周期 API

Console 只监听回环地址，所有生命周期路由都要求有效 Session。浏览器不能写 `/etc`、分配端口或生成 systemd 单元。

- `GET /api/instance-catalog`：列出最新 VPNGate 目录中的国家/地区、可用节点数和资源预览。
- `POST /api/instances/validate`：用 `{"country":"DE"}` 预检创建。
- `POST /api/instances`：原子创建并启动目录中的实例。
- `GET /api/instances`、`GET /api/instances/{id}/status`：查询实例状态。
- `POST /api/instances/{id}/service`：仅接受 `start`、`stop`、`restart`，并只控制安装器管理的单元。
- `DELETE /api/instances/{id}`：要求 `{"confirmation":"id"}`，默认保留数据；永久删除还需 `retain_data:false` 和 `purge_data_confirmation:"purge:id"`。

后端从当前两位国家代码派生规范实例 ID，分配空闲 TUN、策略表和 UI/代理端口，并校验主机冲突、路径和重复项。配置使用 `0600` 权限，`instances.json` 原子更新。创建失败会恢复原目录并移除新建的空资源；删除先停止并禁用服务，默认保留数据。

## systemd 与网络边界

`aimilivpn@.service` 仅保留 `CAP_NET_ADMIN` 和 `CAP_NET_RAW`；`aimilivpn-console.service` 的 capability bounding set 为空。两者启用 `NoNewPrivileges`、`PrivateTmp`、`ProtectHome`、`ProtectSystem=strict`、`UMask=0077`、地址族/命名空间限制和内核/控制组保护。

实例环境文件位于 `/etc/aimilivpn/{country}.env`，权限为 `0600`。JP/US/KR 保留兼容槽位，其他国家从 tun13/table 113/proxy 7931/UI 18791 起分配第一个空闲受管槽位；上游国家列表变化不会重编号。

安装器不修改 DNS 或 `/etc/resolv.conf`。写入 `rp_filter=2` 前会记录原始值，并备份已有 `/etc/sysctl.d/99-aimilivpn.conf`。`ml uninstall --yes` 会停止服务、清理实例策略路由、恢复或移除 AimiliVPN 管理的 sysctl 配置，默认保留数据和源码。

## 正式发布前

Windows 本地测试不能替代 Linux CI 和全新 Ubuntu 实机验收。发布候选必须完成 [`release-acceptance.md`](release-acceptance.md) 中的全部门禁。
