#!/bin/bash
# ============================================================================
# 智鉴黄精 AI 品质检测系统 - 启动脚本 (Linux)
#
# 用法:
#   bash scripts/run.sh
#
# 行为:
#   1. 定位项目根目录 (脚本所在目录的上一级)
#   2. 加载 .env 配置 (HOST / PORT)
#   3. 激活虚拟环境并启动 Streamlit 应用
#
# 环境变量覆盖:
#   HOST / PORT  直接指定监听地址与端口, 优先级高于 .env
#   HJ_FOREGROUND=0  使用 nohup 后台启动, 日志写入 logs/app.log
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

# ----------------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_RESET=$'\033[0m'; C_RED=$'\033[0;31m'; C_GREEN=$'\033[0;32m'
    C_YELLOW=$'\033[0;33m'; C_BLUE=$'\033[0;34m'; C_BOLD=$'\033[1m'
else
    C_RESET=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_BOLD=''
fi

info() { printf '%s[INFO]%s %s\n' "$C_BLUE"   "$C_RESET" "$*"; }
ok()   { printf '%s[ OK ]%s %s\n'  "$C_GREEN"  "$C_RESET" "$*"; }
warn() { printf '%s[WARN]%s %s\n'  "$C_YELLOW" "$C_RESET" "$*"; }
err()  { printf '%s[FAIL]%s %s\n'  "$C_RED"    "$C_RESET" "$*" >&2; }
die()  { err "$*"; exit 1; }

# ----------------------------------------------------------------------------
# 配置加载: 仅读取 HOST / PORT, 不覆盖已导出的同名环境变量
# ----------------------------------------------------------------------------
load_env() {
    local file="$APP_DIR/.env"
    [ -f "$file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|\#*) continue ;;
        esac
        local key="${line%%=*}" value="${line#*=}"
        key="$(printf '%s' "$key" | tr -d '[:space:]')"
        value="$(printf '%s' "$value" | sed "s/^'//;s/'$//;s/^\"//;s/\"\$//")"
        case "$key" in
            HOST|PORT)
                if [ -z "${!key:-}" ]; then
                    export "$key=$value"
                fi
                ;;
        esac
    done < "$file"
}

# ----------------------------------------------------------------------------
# 前置检查
# ----------------------------------------------------------------------------
preflight() {
    [ -f "$APP_DIR/app.py" ] || die "未找到 app.py: $APP_DIR/app.py"
    [ -x "$APP_DIR/venv/bin/python" ] || die "虚拟环境不存在或不可用, 请先运行: bash scripts/install.sh"

    if [ -f "$APP_DIR/.env" ]; then
        if ! grep -qE '^ARK_API_KEY=.+' "$APP_DIR/.env"; then
            warn "ARK_API_KEY 未配置, online 模式将无法调用视觉模型 (demo 模式不受影响)。"
        fi
    else
        warn "未找到 .env 配置文件, 将使用默认配置启动。"
    fi

    mkdir -p "$APP_DIR/logs"
}

# ----------------------------------------------------------------------------
# 端口占用检查
# ----------------------------------------------------------------------------
port_in_use() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
    elif command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
    else
        (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null || return 1
        exec 3>&- 3<&- 2>/dev/null || true
        return 0
    fi
}

# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
load_env

HOST_VALUE="${HOST:-0.0.0.0}"
PORT_VALUE="${PORT:-8501}"

preflight

if port_in_use "$PORT_VALUE"; then
    die "端口 $PORT_VALUE 已被占用。请更换端口 (PORT=xxxx bash scripts/run.sh) 或停止占用进程。"
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source "$APP_DIR/venv/bin/activate"
ok "虚拟环境已激活: $APP_DIR/venv"

info "启动 智鉴黄精 AI 品质检测系统..."
info "监听地址: http://$HOST_VALUE:$PORT_VALUE"

if [ "${HJ_FOREGROUND:-1}" = "1" ]; then
    exec python -m streamlit run "$APP_DIR/app.py" \
        --server.address "$HOST_VALUE" \
        --server.port "$PORT_VALUE" \
        --server.headless true
else
    nohup python -m streamlit run "$APP_DIR/app.py" \
        --server.address "$HOST_VALUE" \
        --server.port "$PORT_VALUE" \
        --server.headless true \
        > "$APP_DIR/logs/app.log" 2>&1 &
    local_bg_pid=$!
    disown "$local_bg_pid" 2>/dev/null || true
    sleep 2
    if kill -0 "$local_bg_pid" 2>/dev/null; then
        ok "应用已在后台启动 (PID: $local_bg_pid)"
        ok "日志: $APP_DIR/logs/app.log"
    else
        err "应用启动失败, 请查看日志: $APP_DIR/logs/app.log"
        exit 1
    fi
fi
