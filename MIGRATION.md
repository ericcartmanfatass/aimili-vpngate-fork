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
