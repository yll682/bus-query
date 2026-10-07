#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { printf '请使用 root 权限运行部署脚本。\n' >&2; exit 1; }
[[ -d /run/systemd/system ]] || { printf '需要正在运行的 systemd。\n' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == debian || "$ID" == ubuntu ]] || { printf '支持 Debian 和 Ubuntu。\n' >&2; exit 1; }

printf '\n候车 · 部署管理\n\n1) 安装 / 更新\n2) 重启服务\n3) 查看状态\n4) 卸载\n5) 退出\n\n'
read -r -p '请选择 [1-5]：' choice
case "$choice" in
    1) action=install ;;
    2) action=restart ;;
    3) action=status ;;
    4) action=uninstall ;;
    5) exit 0 ;;
    *) printf '选项无效。\n' >&2; exit 1 ;;
esac

if [[ "$action" != install ]]; then
    if [[ -f /opt/bus-query/installer.py && ! -L /opt/bus-query/installer.py ]]; then
        python3 /opt/bus-query/installer.py "$action"
        exit 0
    fi
    [[ -e /opt/bus-query ]] || { printf '尚未安装。\n'; exit 0; }
fi

port_args=()
if [[ "$action" == install ]]; then
    if [[ ! -e /opt/bus-query/config.json ]]; then
        read -r -p '监听端口 [8765]：' port
        port=${port:-8765}
        [[ "$port" =~ ^[0-9]{1,5}$ ]] && (( 10#$port >= 1024 && 10#$port <= 65535 )) || {
            printf '端口范围为 1024 至 65535。\n' >&2; exit 1;
        }
        port_args=(--port "$port")
    fi
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl python3 python3-venv
fi
command -v python3 >/dev/null
command -v curl >/dev/null

# 安装程序保存在应用专用缓存目录，运行结束后删除本次下载文件。
cache=/var/cache/bus-query-installer
[[ ! -L "$cache" ]] || { printf '缓存目录不允许使用符号链接。\n' >&2; exit 1; }
install -d -m 700 "$cache"
script=$(mktemp "$cache/installer.XXXXXXXX.py")
unit=$(mktemp "$cache/unit.XXXXXXXX.service")
cleanup() {
    rm -f -- "$script" "$unit"
    if [[ -z "$(ls -A "$cache")" ]]; then rmdir -- "$cache"; fi
}
trap cleanup EXIT
source_url=https://raw.githubusercontent.com/yll682/bus-query/main/deploy
curl --fail --show-error --silent --location --connect-timeout 15 --max-time 120 "$source_url/installer.py" -o "$script"
curl --fail --show-error --silent --location --connect-timeout 15 --max-time 120 "$source_url/bus-query.service" -o "$unit"
python3 "$script" "$action" --unit "$unit" "${port_args[@]}"
