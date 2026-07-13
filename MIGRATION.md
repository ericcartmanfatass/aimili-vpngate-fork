# AimiliVPN Migration Notes

本文档记录从旧脚本式安装迁移到当前 fork 的注意事项。

## 升级来源

当前维护 fork:

```bash
https://github.com/ericcartmanfatass/aimili-vpngate-fork
```

推荐使用当前 fork 的 `install.sh`。安装脚本默认执行 fast-forward 更新；如果本地源码有修改，默认会保留本地内容。只有显式设置 `FORCE_UPDATE=1` 时才会尝试重置到远端分支。

## Web 和 Console 登录配置

新版本使用 PBKDF2 password hash，不应再保存明文登录密码。

旧格式:

```json
{
  "username": "admin",
  "password": "plain-password"
}
```

新格式:

```json
{
  "username": "admin",
  "password_hash": "pbkdf2_sha256$...",
  "secret_path": "..."
}
```

启动时会尽量兼容旧配置并迁移到 `password_hash`。迁移后请确认 `ui_auth.json` 和 `/etc/aimilivpn/console_auth.json` 不再包含 `password` 明文字段。

## 管理面监听与 TLS 迁移

新安装的 Web UI 和 Console 默认监听 `127.0.0.1`。旧配置中显式保存的 `0.0.0.0` 或 `::` 会为了配置兼容继续保留，但启动时会输出高优先级明文公网监听警告。升级后应将下列文件中的 `host` 改为 `127.0.0.1`：

```text
/etc/aimilivpn/console_auth.json
/opt/aimilivpn/vpngate_data/ui_auth.json  # 仅旧单实例安装
```

远程访问迁移为同机 TLS 反向代理，并在对应服务环境文件中显式启用本机代理信任：

```ini
AIMILIVPN_TRUST_PROXY_HEADERS=1
AIMILIVPN_TRUSTED_PROXY_ADDRESSES=127.0.0.1,::1
```

完整的 Nginx/Caddy 示例及 SSH 应急访问方式见 [`docs/reverse-proxy.md`](docs/reverse-proxy.md)。确认 HTTPS 登录响应的 Session Cookie 包含 `Secure; HttpOnly; SameSite=Lax` 后，再从防火墙和云安全组中移除旧的 `8787`/`8788` 公网规则。

## 数据文件

当前默认仍使用 JSON 存储:

```text
nodes.json
state.json
regions.json
quality_results.json
settings.json
ui_auth.json
```

SQLite backend 尚未作为默认存储启用。迁移到 SQLite 前，应先备份上述 JSON 文件。

实验性 SQLite backend 可通过环境变量启用:

```bash
export STORAGE_BACKEND=sqlite
export SQLITE_DB_PATH=/opt/aimilivpn/data/aimilivpn.db
```

未设置时仍保持 JSON 默认存储。`STORAGE_BACKEND` 设置为不支持的值时，启动配置会回退到 `json`。
当前实验性 SQLite backend 覆盖节点、地区、质量结果和 settings repository；`state.json`、`ui_auth.json`、认证文件和运行时临时文件仍保持 JSON/文本文件。

## ml 命令

`/usr/bin/ml` 现在是薄 wrapper:

```bash
cd /opt/aimilivpn
exec /usr/bin/python3 -m aimilivpn.cli.main "$@"
```

这意味着 CLI 逻辑来自项目内 `aimilivpn/cli`，不再由安装脚本内嵌生成大段命令逻辑。

## systemd 单元

当前 systemd 单元增加了基础 hardening:

```ini
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full
```

backend 和 console 服务会限制对系统目录的写入，允许写入安装目录、`/etc/aimilivpn` 和日志目录。如果你在旧系统上遇到 TUN 或 route 权限问题，先查看:

```bash
journalctl -u aimilivpn@jp.service -n 100
```

## 回滚

回滚前建议先备份:

```bash
cp -a /etc/aimilivpn /etc/aimilivpn.backup
cp -a /opt/aimilivpn/data /opt/aimilivpn-data.backup
```

如果需要卸载服务但保留数据:

```bash
ml uninstall --yes
```

删除数据或源码需要额外确认参数，避免误删。
