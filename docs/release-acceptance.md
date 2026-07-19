# v1.0.3 发布验收清单

只有下列项目都具备同一候选 commit 的证据时，才能正式发布。Windows 本地测试用于开发回归，不能替代 Linux CI 或全新 Ubuntu 主机生命周期演练。

## 1. 候选版本身份与源码门禁

记录候选 Tag、完整 commit、发布包 SHA-256、CI 运行链接、操作系统和 Python 版本。必需矩阵为：

- Ubuntu 22.04、24.04；
- CPython 3.10、3.12；
- Node.js 22。

在干净的 Linux 检出目录执行：

```bash
bash scripts/release-acceptance.sh | tee release-source-acceptance.log
git status --short
```

该命令必须成功完成 Python 编译、Shell/JavaScript 语法、完整 Python 测试、恶意 DOM 测试、旧认证与 JSON/SQLite 迁移回滚演练，并确认没有非预期 Git 差异。最终退出码必须为 0，工作区必须干净。日志作为发布证据保存，但不要加入源码包。

## 2. 自动化功能证据

确认测试覆盖并通过以下 v1.0.3 收尾项：

- 初始随机密码只写入 `0600` 一次性凭据文件，日志不出现明文；修改/重置密码后删除旧文件。
- Console 节点中心支持可用性、质量状态、风险等级、风险分数范围、缓存、延迟、更新时间筛选，以及真实数值风险排序。
- 总览统计卡可以跳转到“已连接实例”“高风险节点”和“质量待处理队列”的预设视图。
- 创建、启动、停止、重启、删除、恢复等变更操作在提交前显示影响范围并要求确认；删除数据和恢复删除项使用独立确认。
- “日志与安全”页显示最近备份/恢复、全局数据库健康和逐实例迁移条数/校验摘要；导出日志再次脱敏。
- API/CLI 的错误码、中文消息、存储状态、备份校验和生命周期结果保持一致。
- 前端运行时无外部字体/脚本依赖，不使用危险 HTML 注入点或浏览器持久化存储保存服务端数据。

## 3. 人工安全审查

审查精确候选版本，并记录审查人、日期和每项结论：

- Web 与 Console 默认监听回环地址；IPv6 Web 回退仍是回环地址；公网管理仅使用文档化的 TLS 反向代理。
- 可信回环代理后的 HTTPS 登录设置 `Secure; HttpOnly; SameSite=Lax`；直接 HTTP 不虚假声明传输安全。
- Web/Console 只存 PBKDF2 哈希，凭据修改后撤销受影响 Session，并限制请求体、线程、超时和登录频率。
- 访问日志、应用日志和 JSON 日志会脱敏 secret path、凭据、私钥、Token 和第三方密钥；公开 API 不返回 OpenVPN 正文或第三方原始响应。
- Console 生命周期请求只能选择服务端目录国家，TUN、策略表、端口、路径和 systemd 资源均由后端分配。
- 一次性初始凭据文件权限为 `0600`；安装、启动、审计和错误日志均不包含生成的密码。

测试到代码的映射见 [`../TESTING.md`](../TESTING.md)。任何边界不符合都阻止发布，即使自动化测试通过。

v1.0.3 候选版本的代码辅助安全审查记录见 [`acceptance/v1.0.3-security-review.md`](acceptance/v1.0.3-security-review.md)。

本地浏览器三视口、无障碍、确认流程和离线资源验收记录见 [`acceptance/v1.0.3-browser/README.md`](acceptance/v1.0.3-browser/README.md)。

## 4. 迁移与回滚演练

源码门禁和 CI 每个矩阵成员都必须独立执行：

```bash
python3 scripts/release_migration_drill.py
```

预期 JSON 包含 `"status": "passed"`，确认明文认证字段已移除，报告迁移文档数和回滚校验和，并证明 JSON → SQLite → JSON 回退 → SQLite 再升级后条数与 SHA-256 一致。演练只使用临时目录。

生产升级前仍需按 [`installation.md`](installation.md) 单独备份 `/etc/aimilivpn` 与 `/opt/aimilivpn/data`。

## 5. 全新 Ubuntu 主机生命周期

使用启用 TUN 的全新 Ubuntu 22.04 或 24.04 VPS/VM，并先创建供应商快照。禁止在含用户数据的主机上执行。

1. 安装上一已验证版本，准备代表性的旧 JSON 和认证配置，再使用候选发布包与不可变 `AIMILIVPN_REF` 升级。
2. 确认全新安装只创建 JP；`systemctl is-active aimilivpn-console aimilivpn@jp` 成功；`ss -lntp` 显示 Console、Web 和代理上游只监听回环地址。
3. VPNGate 更新后，从 Console 创建一个非 JP 实例，确认其 TUN、策略表和端口不与 JP 冲突。
4. 连接节点并确认代理出口；断开、重连、重启实例和 Console 后仍可工作。
5. 确认认证配置没有明文 `password`；检查一次性凭据文件权限与删除行为；完成 JSON/SQLite 迁移、备份摘要检查、JSON 回退和再次升级。
6. 分别执行配置备份和完整业务备份；检查差异预览、删除项独立确认、恢复前快照、恢复结果与 SHA-256 状态。
7. 回滚到上一已验证版本并恢复配置/数据，确认保留的 JP 可启动。
8. 重装候选版本，执行 `ml uninstall --yes`，确认服务、实例路由和 AimiliVPN 管理的 sysctl 已移除，数据与源码仍保留。只在这台一次性主机上测试永久删除确认。

保存已脱敏的命令输出、服务状态、监听表、相关 journal 片段和发布包校验和。不得附带密码、Session Cookie、secret path、API Key、代理凭据或 OpenVPN 配置。

## 6. 必需签署

| 门禁 | 必需证据 |
| --- | --- |
| 候选身份 | Tag、完整 commit、发布包 SHA-256 |
| Linux CI | 完整矩阵成功运行链接 |
| 自动化回归 | Python/DOM/语法/迁移门禁日志 |
| 安全审查 | 审查人、日期、六项边界结论 |
| 迁移/回滚 | 演练输出、条数和备份摘要校验和 |
| 全新主机 | OS/镜像、TUN、安装到卸载证据 |
| 文档 | README、MIGRATION、SECURITY、安装与发布说明复核结果 |

任一证据缺失、只完成部分步骤或仅由本地模拟代替，均属于发布阻断项。
