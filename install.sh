#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;36m'
PLAIN='\033[0m'

# 1. Check root permissions
if [ "$(id -u)" != "0" ]; then
    echo -e "${RED}错误: 必须以 root 权限运行此脚本。请使用: sudo bash $0${PLAIN}"
    exit 1
fi

# 2. Check OS distribution and set package manager
OS_TYPE=""
PKG_MGR=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_TYPE=$ID
fi

case "$OS_TYPE" in
    ubuntu|debian)
        PKG_MGR="apt-get"
        export DEBIAN_FRONTEND=noninteractive
        ;;
    alpine)
        PKG_MGR="apk"
        ;;
    centos|rhel|rocky|almalinux|fedora|ol|amzn)
        if command -v dnf >/dev/null 2>&1; then
            PKG_MGR="dnf"
        else
            PKG_MGR="yum"
        fi
        ;;
    *)
        echo -e "${RED}错误: 不支持的操作系统 ($OS_TYPE)！目前仅支持 Ubuntu/Debian/Alpine/CentOS/RHEL/Rocky/AlmaLinux/Fedora/OracleLinux/AmazonLinux。${PLAIN}"
        exit 1
        ;;
esac

echo -e "${BLUE}==========================================================${PLAIN}"
echo -e "${BLUE}        欢迎使用 AimiliVPN 一键源码部署与管理脚本${PLAIN}"
echo -e "${BLUE}==========================================================${PLAIN}"

# 3. Configure GitHub Repository URL
DEFAULT_USER="ericcartmanfatass"
DEFAULT_REPO="aimili-vpngate-fork"

# Allow custom repository override via command line arguments
GITHUB_USER="${1:-${DEFAULT_USER}}"
GITHUB_REPO="${2:-${DEFAULT_REPO}}"

GITHUB_URL="https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"

echo -e "\n${YELLOW}[1/4] 正在安装系统基础依赖...${PLAIN}"
if [ "$PKG_MGR" = "apt-get" ]; then
    echo -e "  -> 正在运行 apt-get update 更新软件源清单..."
    apt-get update -q || true
    echo -e "  -> 正在运行 apt-get install 安装基础依赖包..."
    apt-get install -y openvpn curl git ca-certificates iptables iproute2 psmisc python3
elif [ "$PKG_MGR" = "apk" ]; then
    echo -e "  -> 正在运行 apk update 更新软件源清单..."
    apk update || true
    echo -e "  -> 正在运行 apk add 安装基础依赖包..."
    # bash is required for this script itself and some internal logic
    apk add openvpn curl git ca-certificates iptables iproute2 psmisc python3 bash
elif [ "$PKG_MGR" = "dnf" ] || [ "$PKG_MGR" = "yum" ]; then
    echo -e "  -> 正在运行 $PKG_MGR 安装基础依赖包..."
    if [ "$OS_TYPE" != "fedora" ] && [ "$OS_TYPE" != "amzn" ]; then
        echo -e "     -> 正在安装 EPEL 软件源 (以支持 openvpn)..."
        $PKG_MGR install -y epel-release || true
    fi
    # Try installing packages. Note: iproute or iproute2
    $PKG_MGR install -y openvpn curl git ca-certificates iptables iproute psmisc python3 || \
    $PKG_MGR install -y openvpn curl git ca-certificates iptables iproute2 psmisc python3
fi

# 4. Clone or pull the repository
INSTALL_DIR="/opt/aimilivpn"
SYSTEMD_UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 默认部署分支（在 bate 分支设为 bate；在 main 分支设为 main）
DEFAULT_DEPLOY_BRANCH="${DEFAULT_DEPLOY_BRANCH:-main}"

write_ml_wrapper() {
    cat > /usr/bin/ml <<EOF
#!/usr/bin/env bash
cd "${INSTALL_DIR}"
exec /usr/bin/python3 -m aimilivpn.cli.main "\$@"
EOF
    chmod +x /usr/bin/ml
}

# 自动检测本地已安装版本当前所在的分支
CURRENT_BRANCH=""
if [ -d "${INSTALL_DIR}/.git" ]; then
    CURRENT_BRANCH=$(cd "${INSTALL_DIR}" && git rev-parse --abbrev-ref HEAD 2>/dev/null)
fi
DEPLOY_BRANCH="${CURRENT_BRANCH:-$DEFAULT_DEPLOY_BRANCH}"

echo -e "\n${YELLOW}[2/4] 正在从 GitHub 部署源代码到 ${INSTALL_DIR} (目标分支: ${DEPLOY_BRANCH})...${PLAIN}"
if [ -f "${SCRIPT_DIR}/console_server.py" ]; then
    echo -e "${GREEN}  -> 检测到本地多实例源码，跳过 GitHub 拉取，使用当前目录部署。${PLAIN}"
    mkdir -p "${INSTALL_DIR}"
elif [ -f "${INSTALL_DIR}/.local_dev" ]; then
    echo -e "${GREEN}检测到本地开发模式 (.local_dev)，跳过 git pull/reset 保持本地修改。${PLAIN}"
else
    if [ -d "${INSTALL_DIR}" ]; then
        echo -e "  -> 目录 ${INSTALL_DIR} 已存在，正在安全更新本地源码..."
        cd "${INSTALL_DIR}"
        git fetch --all || true
        git checkout "${DEPLOY_BRANCH}" || git checkout -b "${DEPLOY_BRANCH}" "origin/${DEPLOY_BRANCH}" || true
        echo -e "  -> 正在执行 fast-forward 更新 origin/${DEPLOY_BRANCH} ..."
        if git pull --ff-only origin "${DEPLOY_BRANCH}"; then
            echo -e "${GREEN}  -> 源码更新成功！${PLAIN}"
        else
            if [ "${FORCE_UPDATE:-0}" = "1" ]; then
                echo -e "${YELLOW}  -> FORCE_UPDATE=1，正在强制重置本地源码至 origin/${DEPLOY_BRANCH} ...${PLAIN}"
                if git reset --hard "origin/${DEPLOY_BRANCH}"; then
                    echo -e "${GREEN}  -> 源码已强制更新。${PLAIN}"
                else
                    echo -e "${YELLOW}  -> 警告: git reset 失败，将保留当前本地源码并继续安装。${PLAIN}"
                fi
            else
                echo -e "${YELLOW}  -> 警告: fast-forward 更新失败，可能存在本地修改或分叉提交。${PLAIN}"
                echo -e "${YELLOW}  -> 已保留当前本地源码。确认要覆盖时，可重新运行: FORCE_UPDATE=1 bash install.sh${PLAIN}"
            fi
        fi
    else
        echo -e "  -> 正在克隆 GitHub 仓库 ${GITHUB_URL} (分支: ${DEPLOY_BRANCH}) ..."
        if git clone -b "${DEPLOY_BRANCH}" "${GITHUB_URL}" "${INSTALL_DIR}"; then
            echo -e "${GREEN}  -> 克隆成功！${PLAIN}"
        else
            echo -e "  -> 尝试默认克隆..."
            if git clone "${GITHUB_URL}" "${INSTALL_DIR}"; then
                cd "${INSTALL_DIR}"
                git checkout "${DEPLOY_BRANCH}" || git checkout -b "${DEPLOY_BRANCH}" "origin/${DEPLOY_BRANCH}" || true
                echo -e "${GREEN}  -> 克隆成功！${PLAIN}"
            else
                echo -e "${RED}  -> 错误: 无法克隆仓库 ${GITHUB_URL}，请检查网络！${PLAIN}"
                exit 1
            fi
        fi
    fi
fi

if [ -f "${SCRIPT_DIR}/console_server.py" ]; then
    echo -e "  -> Syncing local multi-instance source files into ${INSTALL_DIR} ..."
    mkdir -p "${INSTALL_DIR}"
    for src_file in install.sh proxy_server.py vpngate_manager.py vpn_utils.py console_server.py README.md LICENSE .gitignore .gitattributes; do
        if [ -f "${SCRIPT_DIR}/${src_file}" ]; then
            src_path="$(readlink -f "${SCRIPT_DIR}/${src_file}")"
            dst_path="$(readlink -f "${INSTALL_DIR}/${src_file}" 2>/dev/null || printf '%s/%s' "${INSTALL_DIR}" "${src_file}")"
            if [ "$src_path" != "$dst_path" ]; then
                cp "${SCRIPT_DIR}/${src_file}" "${INSTALL_DIR}/${src_file}"
            fi
        fi
    done
    for src_dir in aimilivpn tests; do
        if [ -d "${SCRIPT_DIR}/${src_dir}" ]; then
            rm -rf "${INSTALL_DIR:?}/${src_dir}"
            cp -a "${SCRIPT_DIR}/${src_dir}" "${INSTALL_DIR}/${src_dir}"
        fi
    done
    find "${INSTALL_DIR}" -maxdepth 1 -type f \( -name '*.py' -o -name '*.sh' \) -exec sed -i 's/\r$//' {} \;
fi

# 5. Configure Service
echo -e "\n${YELLOW}[3/4] 正在配置系统服务...${PLAIN}"
if command -v systemctl >/dev/null 2>&1; then
    echo -e "  -> Detected systemd, configuring multi-instance backend and single console..."
    mkdir -p /etc/aimilivpn

    if [ ! -f /etc/aimilivpn/instance_api_token ]; then
        python3 -c "import secrets; print(secrets.token_urlsafe(32))" > /etc/aimilivpn/instance_api_token
        chmod 600 /etc/aimilivpn/instance_api_token
    fi
    INSTANCE_API_TOKEN="$(cat /etc/aimilivpn/instance_api_token)"

    declare -A TUN_DEV_MAP=( [JP]=tun10 [US]=tun11 [KR]=tun12 )
    declare -A POLICY_MAP=( [JP]=110 [US]=111 [KR]=112 )
    declare -A PROXY_PORT_MAP=( [JP]=7928 [US]=7929 [KR]=7930 )
    declare -A UI_PORT_MAP=( [JP]=18788 [US]=18789 [KR]=18790 )
    COUNTRIES="${COUNTRIES:-JP,US,KR}"

    if systemctl list-unit-files aimilivpn.service >/dev/null 2>&1; then
        systemctl disable --now aimilivpn.service >/dev/null 2>&1 || true
    fi

    mkdir -p "${SYSTEMD_UNIT_DIR}"
    echo -e "  -> Writing ${SYSTEMD_UNIT_DIR}/aimilivpn@.service ..."
    cat > "${SYSTEMD_UNIT_DIR}/aimilivpn@.service" <<EOF
[Unit]
Description=AimiliVPN OpenVPN Manager instance %i
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 -m aimilivpn.system.vpngate_manager
Restart=always
RestartSec=5
EnvironmentFile=/etc/aimilivpn/%i.env
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full
ReadWritePaths=${INSTALL_DIR} /etc/aimilivpn /var/log/aimilivpn

[Install]
WantedBy=multi-user.target
EOF

    python3 - <<'PY'
import json
import os
import secrets
import string
from pathlib import Path
from aimilivpn.core.auth import hash_password

cfg_dir = Path("/etc/aimilivpn")
auth_file = cfg_dir / "console_auth.json"
if not auth_file.exists():
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(16))
    secret_path = "console" + "".join(secrets.choice(alphabet) for _ in range(10))
    auth_file.write_text(json.dumps({
        "username": "admin",
        "password_hash": hash_password(password),
        "secret_path": secret_path,
        "host": "0.0.0.0",
        "port": 8788,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(auth_file, 0o600)
PY

    IFS=',' read -ra CC_LIST <<< "$COUNTRIES"
    INSTANCES_JSON='{"instances":['
    FIRST_JSON=1
    for CC in "${CC_LIST[@]}"; do
        CC="${CC^^}"
        if [ -z "${TUN_DEV_MAP[$CC]:-}" ]; then
            echo -e "${YELLOW}  -> Skipping unsupported country ${CC}; supported: JP/US/KR${PLAIN}"
            continue
        fi
        CC_LO="${CC,,}"
        DATA_DIR="${INSTALL_DIR}/data/${CC_LO}"
        mkdir -p "$DATA_DIR"
        cat > "/etc/aimilivpn/${CC_LO}.env" <<EOF
INSTANCE_ID=${CC_LO}
TUN_DEV=${TUN_DEV_MAP[$CC]}
POLICY_TABLE=${POLICY_MAP[$CC]}
LOCAL_PROXY_HOST=127.0.0.1
LOCAL_PROXY_PORT=${PROXY_PORT_MAP[$CC]}
UI_HOST=127.0.0.1
UI_PORT=${UI_PORT_MAP[$CC]}
VPNGATE_DATA_DIR=${DATA_DIR}
ALLOWED_COUNTRIES=${CC}
EXCLUDE_DATACENTER=1
INSTANCE_API_TOKEN=${INSTANCE_API_TOKEN}
NODE_TEST_WORKERS=2
MAX_MAINTENANCE_TEST_NODES=18
OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS=8
NODE_RETEST_INTERVAL_SECONDS=21600
EOF
        chmod 600 "/etc/aimilivpn/${CC_LO}.env"
        if [ "$FIRST_JSON" -eq 0 ]; then
            INSTANCES_JSON="${INSTANCES_JSON},"
        fi
        FIRST_JSON=0
        INSTANCES_JSON="${INSTANCES_JSON}{\"id\":\"${CC_LO}\",\"country\":\"${CC}\",\"service\":\"aimilivpn@${CC_LO}.service\",\"env_file\":\"/etc/aimilivpn/${CC_LO}.env\",\"data_dir\":\"${DATA_DIR}\",\"ui_host\":\"127.0.0.1\",\"ui_port\":${UI_PORT_MAP[$CC]},\"proxy_host\":\"127.0.0.1\",\"proxy_port\":${PROXY_PORT_MAP[$CC]},\"tun_dev\":\"${TUN_DEV_MAP[$CC]}\",\"policy_table\":${POLICY_MAP[$CC]}}"
        echo -e "  -> ${CC}: ${TUN_DEV_MAP[$CC]}, proxy ${PROXY_PORT_MAP[$CC]}, backend UI ${UI_PORT_MAP[$CC]}"
    done
    INSTANCES_JSON="${INSTANCES_JSON}]}"
    printf '%s\n' "$INSTANCES_JSON" > /etc/aimilivpn/instances.json
    chmod 600 /etc/aimilivpn/instances.json

    cat > /etc/aimilivpn/console.env <<EOF
AIMILIVPN_CONFIG_DIR=/etc/aimilivpn
AIMILIVPN_INSTALL_DIR=${INSTALL_DIR}
AIMILIVPN_INSTANCES_FILE=/etc/aimilivpn/instances.json
AIMILIVPN_CONSOLE_AUTH=/etc/aimilivpn/console_auth.json
INSTANCE_API_TOKEN=${INSTANCE_API_TOKEN}
EOF
    chmod 600 /etc/aimilivpn/console.env

    echo -e "  -> Writing ${SYSTEMD_UNIT_DIR}/aimilivpn-console.service ..."
    cat > "${SYSTEMD_UNIT_DIR}/aimilivpn-console.service" <<EOF
[Unit]
Description=AimiliVPN unified web console
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 -m aimilivpn.system.console_server
Restart=always
RestartSec=5
EnvironmentFile=/etc/aimilivpn/console.env
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full
ReadWritePaths=/etc/aimilivpn /var/log/aimilivpn

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    for CC in "${CC_LIST[@]}"; do
        CC_LO="${CC,,}"
        [ -f "/etc/aimilivpn/${CC_LO}.env" ] && systemctl enable "aimilivpn@${CC_LO}.service" >/dev/null 2>&1 || true
    done
    systemctl enable aimilivpn-console.service >/dev/null 2>&1 || true
elif command -v rc-service >/dev/null 2>&1; then
    echo -e "  -> 检测到 OpenRC，正在创建服务配置 /etc/init.d/aimilivpn ..."
    cat > /etc/init.d/aimilivpn <<EOF
#!/sbin/openrc-run

description="AimiliVPN OpenVPN Manager with HTTP/SOCKS5 Proxy"
command="/usr/bin/python3"
command_args="-m aimilivpn.system.vpngate_manager"
command_background="yes"
directory="${INSTALL_DIR}"
pidfile="/run/aimilivpn.pid"

depend() {
    need net
    after firewall
}
EOF
    chmod +x /etc/init.d/aimilivpn
    rc-update add aimilivpn default
else
    echo -e "${YELLOW}警告: 未能检测到 systemd 或 OpenRC，请手动管理服务。${PLAIN}"
fi

# 6. Configure global command shortcut "ml"
echo -e "\n${YELLOW}[4/4] 正在创建全局命令快捷接口 'ml'...${PLAIN}"
echo -e "  -> 正在写入管理脚本 /usr/bin/ml ..."
write_ml_wrapper


# 7. Configure Custom parameters (First-time installation check)
if [ ! -f "${SYSTEMD_UNIT_DIR}/aimilivpn@.service" ] && [ ! -f /lib/systemd/system/aimilivpn@.service ] && [ ! -f /usr/lib/systemd/system/aimilivpn@.service ]; then
AUTH_FILE="${INSTALL_DIR}/vpngate_data/ui_auth.json"
mkdir -p "${INSTALL_DIR}/vpngate_data"

is_custom="n"
if [ ! -f "$AUTH_FILE" ]; then
    if [ -t 0 ]; then
        echo -e "\n${YELLOW}检测到是首次安装，是否需要自定义配置网页端参数（端口/安全后缀/登录账号密码）？${PLAIN}"
        read -p "是否自定义配置？[y/N]: " is_custom
    else
        echo -e "\n${YELLOW}检测到是非交互式/无TTY环境安装，已自动跳过网页端参数自定义配置，采用默认随机参数部署。${PLAIN}"
    fi
    
    # Initialize defaults
    UI_PORT=8787
    # generate random secret suffix (12 chars alphanumeric)
    SECRET_PATH=$(python3 -c "import secrets, string; chars = string.ascii_letters + string.digits; print(''.join(secrets.choice(chars) for _ in range(12)))")
    # generate random password
    UI_PASSWORD=$(python3 -c "
import secrets, string
chars = string.ascii_letters + string.digits
while True:
    pwd = ''.join(secrets.choice(chars) for _ in range(12))
    if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd):
        print(pwd)
        break
")
    UI_USERNAME=$(python3 -c "
import secrets, string
chars = string.ascii_letters + string.digits
while True:
    uname = ''.join(secrets.choice(chars) for _ in range(12))
    if uname[0].isalpha() and any(c.islower() for c in uname) and any(c.isupper() for c in uname) and any(c.isdigit() for c in uname):
        print(uname)
        break
")

    if [[ "$is_custom" =~ ^[Yy]$ ]]; then
        # Step-by-step custom inputs
        # 1. Custom port
        while true; do
            read -p "请输入自定义管理端口 [1-65535, 默认 8787]: " input_port
            if [ -z "$input_port" ]; then
                UI_PORT=8787
                break
            fi
            if [[ "$input_port" =~ ^[0-9]+$ ]] && [ "$input_port" -ge 1 ] && [ "$input_port" -le 65535 ]; then
                UI_PORT=$input_port
                break
            else
                echo -e "${RED}输入错误: 端口必须是 1 到 65535 之间的数字！${PLAIN}"
            fi
        done
        
        # 2. Custom suffix
        while true; do
            read -p "请输入网页登录自定义安全后缀 [字母与数字组合, 默认随机]: " input_suffix
            if [ -z "$input_suffix" ]; then
                break
            fi
            if [[ "$input_suffix" =~ ^[A-Za-z0-9]+$ ]]; then
                SECRET_PATH=$input_suffix
                break
            else
                echo -e "${RED}输入错误: 后缀仅能由英文字母和数字组成！${PLAIN}"
            fi
        done
        
        # 3. Custom login username and password
        read -p "请输入登录账号 [默认 $UI_USERNAME]: " input_user
        if [ -n "$input_user" ]; then
            UI_USERNAME=$input_user
        fi
        
        while true; do
            read -p "请输入登录密码 [默认随机生成, 建议包含字母、数字与符号]: " input_pass
            if [ -z "$input_pass" ]; then
                break
            fi
            if [ ${#input_pass} -ge 4 ]; then
                UI_PASSWORD=$input_pass
                break
            else
                echo -e "${RED}输入错误: 密码长度不能少于 4 位！${PLAIN}"
            fi
        done
    fi

    # Write config JSON. Values are passed as argv to avoid breaking Python code
    # when username/password contain quotes, backslashes, or shell metacharacters.
    python3 - "$AUTH_FILE" "$UI_PORT" "$SECRET_PATH" "$UI_USERNAME" "$UI_PASSWORD" <<'PY'
import json
import sys
from aimilivpn.core.auth import hash_password

auth_file, ui_port, secret_path, username, password = sys.argv[1:6]
cfg = {
    "host": "::",
    "port": int(ui_port),
    "proxy_port": 7928,
    "secret_path": secret_path,
    "username": username,
    "password_hash": hash_password(password),
}
with open(auth_file, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
PY
fi
fi

# 8. Start service
# 8.5 Persist network parameters needed for policy routing.
echo -e "\n正在写入持久化网络参数 (rp_filter=2 以支持策略路由)..."
if [ -d "/etc/sysctl.d" ]; then
    cat > /etc/sysctl.d/99-aimilivpn.conf <<EOF
net.ipv4.conf.all.rp_filter = 2
net.ipv4.conf.default.rp_filter = 2
EOF
    sysctl -p /etc/sysctl.d/99-aimilivpn.conf >/dev/null 2>&1 || true
else
    echo -e "${YELLOW}Warning: /etc/sysctl.d is unavailable; applying rp_filter for this boot only and leaving /etc/sysctl.conf untouched.${PLAIN}"
    sysctl -w net.ipv4.conf.all.rp_filter=2 >/dev/null 2>&1 || true
    sysctl -w net.ipv4.conf.default.rp_filter=2 >/dev/null 2>&1 || true
fi

if [ -f "${SYSTEMD_UNIT_DIR}/aimilivpn@.service" ] || [ -f /lib/systemd/system/aimilivpn@.service ] || [ -f /usr/lib/systemd/system/aimilivpn@.service ]; then
    echo -e "\nStarting AimiliVPN multi-instance backend and unified console..."
    if command -v systemctl >/dev/null 2>&1; then
        if [ -f /etc/aimilivpn/instances.json ]; then
            for svc in $(python3 - <<'PY'
import json
data = json.load(open("/etc/aimilivpn/instances.json", encoding="utf-8"))
for item in data.get("instances", []):
    print(item.get("service", ""))
PY
            ); do
                [ -n "$svc" ] && systemctl restart "$svc" || true
            done
        fi
        systemctl restart aimilivpn-console.service || true
    fi
    echo -e "${YELLOW}Initial node fetching and VPN connection run in the background. Use 'ml status' to monitor.${PLAIN}"
else
echo -e "\n正在启动 AimiliVPN 服务并初始化网络..."
if command -v systemctl >/dev/null 2>&1; then
    systemctl restart aimilivpn.service || true
elif command -v rc-service >/dev/null 2>&1; then
    rc-service aimilivpn restart || true
fi

# Wait and poll for node loading and active connection
echo -e "\n正在等待 AimiliVPN 首次获取节点并建立加密通道 (此过程可能需要 5-30 秒)..."
ACTIVE_ID=""
LAST_MSG=""
for i in {1..90}; do
    if [ -f "${INSTALL_DIR}/vpngate_data/state.json" ]; then
        ACTIVE_ID=$(python3 -c "import json; print(json.load(open('${INSTALL_DIR}/vpngate_data/state.json')).get('active_openvpn_node_id', ''))" 2>/dev/null || echo "")
        IS_CONN=$(python3 -c "import json; print(json.load(open('${INSTALL_DIR}/vpngate_data/state.json')).get('is_connecting', False))" 2>/dev/null || echo "False")
        CUR_MSG=$(python3 -c "import json; print(json.load(open('${INSTALL_DIR}/vpngate_data/state.json')).get('last_check_message', ''))" 2>/dev/null || echo "")
        
        if [ "$IS_CONN" = "False" ] || [ "$IS_CONN" = "false" ]; then
            if [ -n "$ACTIVE_ID" ]; then
                echo -e "  -> ${GREEN}[已就绪]${PLAIN} 首次节点连接成功，活动节点: ${GREEN}$ACTIVE_ID${PLAIN}"
                break
            else
                if [ -n "$CUR_MSG" ] && [ "$CUR_MSG" != "$LAST_MSG" ]; then
                    echo -e "  -> 提示: ${YELLOW}${CUR_MSG}${PLAIN}"
                    LAST_MSG="$CUR_MSG"
                fi
            fi
        else
            if [ -n "$CUR_MSG" ] && [ "$CUR_MSG" != "$LAST_MSG" ]; then
                echo -e "  -> 状态: ${YELLOW}${CUR_MSG}${PLAIN}"
                LAST_MSG="$CUR_MSG"
            fi
        fi
    else
        echo -n "."
    fi
    sleep 1
done
if [ -z "$ACTIVE_ID" ]; then
    echo -e "  -> ${YELLOW}[加载超时]${PLAIN} 首次节点获取或连接超时，将在后台继续尝试..."
fi
fi

SECRET_PATH="EJsW2EeBo9lY"
USERNAME="未配置"
UI_PORT=8787
PROXY_PORT=7928
AUTH_FILE="${INSTALL_DIR}/vpngate_data/ui_auth.json"
if [ -f "$AUTH_FILE" ]; then
    SECRET_PATH=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('secret_path', 'EJsW2EeBo9lY'))" 2>/dev/null || echo "EJsW2EeBo9lY")
    USERNAME=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('username', '未配置'))" 2>/dev/null || echo "未配置")
    UI_PORT=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('port', 8787))" 2>/dev/null || echo "8787")
    PROXY_PORT=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('proxy_port', 7928))" 2>/dev/null || echo "7928")
fi

# Get VPS public IP
echo -e "正在获取 VPS 公网 IP..."
PUBLIC_IP=$(curl -s --max-time 3 https://api.ipify.org || curl -s --max-time 3 https://ifconfig.me || curl -s --max-time 3 icanhazip.com || echo "您的服务器公网IP")
if [ -d "${INSTALL_DIR}/vpngate_data" ]; then
    echo -n "$PUBLIC_IP" > "${INSTALL_DIR}/vpngate_data/public_ip.txt"
fi

# Get VPS public IPv6
echo -e "正在获取 VPS 公网 IPv6..."
PUBLIC_IPV6=$(curl -6 -s --max-time 3 https://api.ipify.org || curl -6 -s --max-time 3 https://ifconfig.me || curl -6 -s --max-time 3 icanhazip.com || echo "")

if [ -f /etc/aimilivpn/instances.json ] && [ -f /etc/aimilivpn/console_auth.json ]; then
    python3 - "$PUBLIC_IP" <<'PY'
import json
import sys
from pathlib import Path

public_ip = sys.argv[1]
instances = json.load(open("/etc/aimilivpn/instances.json", encoding="utf-8")).get("instances", [])
for item in instances:
    data_dir = Path(item.get("data_dir", ""))
    if data_dir:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "public_ip.txt").write_text(public_ip, encoding="utf-8")
PY
    CONSOLE_SECRET=$(python3 -c "import json; print(json.load(open('/etc/aimilivpn/console_auth.json')).get('secret_path',''))" 2>/dev/null || echo "")
    CONSOLE_USER=$(python3 -c "import json; print(json.load(open('/etc/aimilivpn/console_auth.json')).get('username','admin'))" 2>/dev/null || echo "admin")
    CONSOLE_PORT=$(python3 -c "import json; print(json.load(open('/etc/aimilivpn/console_auth.json')).get('port',8788))" 2>/dev/null || echo "8788")
    echo -e "\n${GREEN}==========================================================${PLAIN}"
    echo -e "${GREEN}             AimiliVPN multi-instance deployment complete${PLAIN}"
    echo -e "${GREEN}==========================================================${PLAIN}"
    echo -e "  * Unified console:  ${BLUE}http://${PUBLIC_IP}:${CONSOLE_PORT}/${CONSOLE_SECRET}/${PLAIN}"
    if [ -n "$PUBLIC_IPV6" ]; then
        echo -e "  * Unified console (IPv6):  ${BLUE}http://[${PUBLIC_IPV6}]:${CONSOLE_PORT}/${CONSOLE_SECRET}/${PLAIN}"
    fi
    echo -e "  * Console username: ${YELLOW}${CONSOLE_USER}${PLAIN}"
    echo -e "  * Console password: ${YELLOW}set; use the Web UI to change it${PLAIN}"
    echo -e " --------------------------------------------------------"
    python3 - <<'PY'
import json
data = json.load(open("/etc/aimilivpn/instances.json", encoding="utf-8"))
for item in data.get("instances", []):
    print(f"  * [{item.get('country')}] proxy: socks5://127.0.0.1:{item.get('proxy_port')}  service: {item.get('service')}")
PY
    echo -e " --------------------------------------------------------"
    echo -e "  * Overview:         ${YELLOW}ml status${PLAIN}"
    echo -e "  * Logs:             ${YELLOW}ml logs${PLAIN}"
    echo -e "  * Restart services: ${YELLOW}ml restart${PLAIN}"
    echo -e "  * Web URLs:         ${YELLOW}ml web${PLAIN}"
    echo -e "  * Password status:  ${YELLOW}ml password${PLAIN}"
    echo -e "=========================================================="
    echo
    exit 0
fi

echo -e "\n${GREEN}==========================================================${PLAIN}"
echo -e "${GREEN}             AimiliVPN 源码一键部署已完成！${PLAIN}"
echo -e "${GREEN}==========================================================${PLAIN}"
echo -e "  * 网页控制面板:  ${BLUE}http://${PUBLIC_IP}:${UI_PORT}/${SECRET_PATH}/${PLAIN}"
if [ -n "$PUBLIC_IPV6" ]; then
    echo -e "  * 网页控制面板(IPv6):  ${BLUE}http://[${PUBLIC_IPV6}]:${UI_PORT}/${SECRET_PATH}/${PLAIN}"
fi
echo -e "  * 网页管理账号:  ${YELLOW}${USERNAME}${PLAIN}"
echo -e "  * Web password:    ${YELLOW}set; use the Web UI to change it${PLAIN}"
echo -e "  * HTTP/SOCKS5 代理端口:  ${BLUE}http://127.0.0.1:${PROXY_PORT}/${PLAIN}  或  ${BLUE}http://[::1]:${PROXY_PORT}/${PLAIN}"
echo -e " --------------------------------------------------------"
echo -e "  * 快速状态指令:   ${YELLOW}ml status${PLAIN}  或  ${YELLOW}ml${PLAIN}"
echo -e "  * 查看实时日志:   ${YELLOW}ml logs${PLAIN}"
echo -e "  * Web URLs:        ${YELLOW}ml web${PLAIN}"
echo -e "  * Password status: ${YELLOW}ml password${PLAIN}"
echo -e "  * 停止服务:       ${YELLOW}ml stop${PLAIN}"
echo -e "  * 重启服务:       ${YELLOW}ml restart${PLAIN}"
echo -e "=========================================================="
echo
