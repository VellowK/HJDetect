#!/bin/bash
# ============================================================================
# 智鉴黄精 AI 品质检测系统 - 环境检查脚本 (Linux)
#
# 用法:
#   bash scripts/check.sh
#
# 检查项:
#   Python / pip / 虚拟环境 / 项目依赖 / .env / API Key 是否存在 (不输出内容)
#   模型配置 / 网络 / 服务端口 / Caddy + HTTPS (如已配置)
#
# 退出码: 0 = 全部通过, 1 = 存在失败项
# ============================================================================

set -uo pipefail

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

PASS=0
WARN=0
FAIL=0

pass() { printf '  %s[PASS]%s %s\n' "$C_GREEN"  "$C_RESET" "$*"; PASS=$((PASS + 1)); }
fail() { printf '  %s[FAIL]%s %s\n' "$C_RED"    "$C_RESET" "$*"; FAIL=$((FAIL + 1)); }
warn() { printf '  %s[WARN]%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; WARN=$((WARN + 1)); }
info() { printf '  %s[INFO]%s %s\n' "$C_BLUE"   "$C_RESET" "$*"; }

section() { printf '\n%s==> %s%s\n' "$C_BOLD" "$*" "$C_RESET"; }

summary() {
    printf '\n%s==============================================================%s\n' "$C_BOLD" "$C_RESET"
    printf '  检查完成: %s通过 %d%s  %s警告 %d%s  %s失败 %d%s\n' \
        "$C_GREEN" "$PASS" "$C_RESET" \
        "$C_YELLOW" "$WARN" "$C_RESET" \
        "$C_RED" "$FAIL" "$C_RESET"
    printf '%s==============================================================%s\n' "$C_BOLD" "$C_RESET"
    if [ "$FAIL" -gt 0 ]; then
        exit 1
    fi
    exit 0
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

port_listening() {
    if command_exists ss; then
        ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
    elif command_exists netstat; then
        netstat -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
    else
        (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null || return 1
        exec 3>&- 3<&- 2>/dev/null || true
        return 0
    fi
}

env_get() {
    # env_get <文件> <KEY> -> 去引号后的值
    local value=""
    value="$(grep -E "^$2=" "$1" 2>/dev/null | tail -n1 | cut -d= -f2-)"
    printf '%s' "$value" | sed "s/^'//;s/'\$//;s/^\"//;s/\"\$//"
}

version_ge() { [ "$(printf '%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]; }

# ----------------------------------------------------------------------------
# 1. Python
# ----------------------------------------------------------------------------
check_python() {
    section "Python 环境"
    local py=""
    if [ -x "$APP_DIR/venv/bin/python" ]; then
        py="$APP_DIR/venv/bin/python"
    elif command_exists python3; then
        py="python3"
    elif command_exists python; then
        py="python"
    fi

    if [ -z "$py" ]; then
        fail "未找到 Python, 请先运行 scripts/install.sh"
        return 1
    fi

    local ver
    ver="$("$py" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo "?")"
    if version_ge "${ver%%.*}.999" "3.8.999" || [ "$(printf '%s' "$ver" | cut -d. -f1-2 | (read a b; echo $((a * 100 + b))))" -ge 308 ]; then
        pass "Python: $ver ($py)"
    else
        fail "Python 版本过低: $ver (需要 3.8+)"
    fi

    # pip
    if "$py" -m pip --version >/dev/null 2>&1; then
        pass "pip: $("$py" -m pip --version 2>/dev/null | awk '{print $2}')"
    else
        fail "pip 不可用"
    fi
}

# ----------------------------------------------------------------------------
# 2. 虚拟环境与依赖
# ----------------------------------------------------------------------------
check_venv() {
    section "虚拟环境与依赖"
    local venv_py="$APP_DIR/venv/bin/python"
    if [ -x "$venv_py" ]; then
        pass "虚拟环境: $APP_DIR/venv"
    else
        fail "虚拟环境不存在 ($APP_DIR/venv), 请先运行 scripts/install.sh"
        return 1
    fi

    if [ ! -f "$APP_DIR/requirements.txt" ]; then
        warn "未找到 requirements.txt, 跳过依赖逐项校验。"
        return 0
    fi

    local missing=0 dep=""
    while IFS= read -r dep || [ -n "$dep" ]; do
        dep="$(printf '%s' "$dep" | sed 's/[[:space:]]*#.*//;s/^[[:space:]]*//;s/[[:space:]]*$//')"
        case "$dep" in
            ''|-*) continue ;;
        esac
        local pkg="${dep%%[=<>~!]*}"
        pkg="${pkg%%\[*\]*}"
        [ -z "$pkg" ] && continue
        if ! "$venv_py" -c "import importlib.metadata; importlib.metadata.distribution('$pkg')" >/dev/null 2>&1; then
            fail "缺少依赖: $pkg"
            missing=1
        fi
    done < "$APP_DIR/requirements.txt"

    if [ "$missing" -eq 0 ]; then
        pass "requirements.txt 依赖全部满足"
    fi
}

# ----------------------------------------------------------------------------
# 3. .env 配置
# ----------------------------------------------------------------------------
check_env() {
    section ".env 配置"
    local file="$APP_DIR/.env"
    if [ ! -f "$file" ]; then
        fail ".env 文件不存在: $file"
        return 1
    fi
    pass ".env 文件存在: $file"

    # 权限
    local perms
    perms="$(stat -c '%a' "$file" 2>/dev/null || stat -f '%Lp' "$file" 2>/dev/null || echo 'unknown')"
    if [ "$perms" = "600" ] || [ "$perms" = "400" ]; then
        pass ".env 文件权限: $perms"
    else
        warn ".env 文件权限为 $perms, 建议执行: chmod 600 $file"
    fi

    # API Key (仅检查是否存在, 不输出内容)
    if grep -qE '^ARK_API_KEY=.+' "$file"; then
        local key_len
        key_len="$("$APP_DIR/venv/bin/python" - <<PYEOF 2>/dev/null || echo "?"
import re, pathlib
text = pathlib.Path("$file").read_text(encoding="utf-8", errors="ignore")
m = re.search(r'^ARK_API_KEY=(.+)$', text, re.M)
v = (m.group(1) if m else "").strip().strip("'\"")
print(len(v))
PYEOF
)"
        if [ "$key_len" = "?" ]; then
            pass "API Key: 已配置 (长度未知)"
        elif [ "$key_len" -ge 20 ] 2>/dev/null; then
            pass "API Key: 已配置 (长度 $key_len)"
        else
            warn "API Key: 已配置但长度过短 ($key_len), 请确认是否填写完整。"
        fi
    else
        fail "API Key 未配置 (online 模式将无法调用视觉模型)"
    fi

    # ARK_BASE_URL / ARK_MODEL / APP_MODE / HOST / PORT
    local url model mode host port
    url="$(env_get "$file" ARK_BASE_URL)"
    model="$(env_get "$file" ARK_MODEL)"
    mode="$(env_get "$file" APP_MODE)"
    host="$(env_get "$file" HOST)"
    port="$(env_get "$file" PORT)"

    if [ -n "$url" ]; then
        pass "ARK_BASE_URL: $url"
    else
        fail "ARK_BASE_URL 未配置"
    fi
    if [ -n "$model" ]; then
        pass "ARK_MODEL: $model"
    else
        fail "ARK_MODEL 未配置"
    fi
    case "$mode" in
        online) pass "APP_MODE: online" ;;
        demo)   pass "APP_MODE: demo (演示容灾模式)" ;;
        "")     warn "APP_MODE 未配置, 默认按 online 处理。" ;;
        *)      warn "APP_MODE 值异常: $mode (应为 online / demo)" ;;
    esac
    if [ -n "$host" ]; then
        pass "HOST: $host"
    else
        warn "HOST 未配置, 默认 0.0.0.0"
    fi
    if printf '%s' "$port" | grep -qE '^[0-9]+$'; then
        pass "PORT: $port"
    else
        warn "PORT 未配置或无效, 默认 8501"
    fi
}

# ----------------------------------------------------------------------------
# 4. 网络连接
# ----------------------------------------------------------------------------
check_network() {
    section "网络连接"
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 6 --max-time 12 https://www.baidu.com 2>/dev/null || true)"
    if [ -n "$code" ] && [ "$code" != "000" ]; then
        pass "互联网可达 (百度返回 HTTP $code)"
    else
        fail "无法访问互联网 (curl https://www.baidu.com 超时或失败)"
    fi

    # ARK Endpoint 可达性
    local file="$APP_DIR/.env" url=""
    [ -f "$file" ] && url="$(env_get "$file" ARK_BASE_URL)"
    if [ -n "$url" ]; then
        code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 6 --max-time 12 "$url" 2>/dev/null || true)"
        if [ -n "$code" ] && [ "$code" != "000" ]; then
            pass "ARK Endpoint 可达: $url (HTTP $code)"
        else
            warn "ARK Endpoint 不可达: $url (可能为防火墙或网络问题)"
        fi
    fi
}

# ----------------------------------------------------------------------------
# 5. 服务端口
# ----------------------------------------------------------------------------
check_port() {
    section "服务端口"
    local file="$APP_DIR/.env" port="8501"
    [ -f "$file" ] && port="$(env_get "$file" PORT)"
    printf '%s' "$port" | grep -qE '^[0-9]+$' || port="8501"

    if port_listening "$port"; then
        local code
        code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 6 "http://127.0.0.1:$port/_stcore/health" 2>/dev/null || true)"
        if [ "$code" = "200" ]; then
            pass "应用运行中: http://127.0.0.1:$port (健康检查 HTTP $code)"
        else
            warn "端口 $port 被占用但健康检查失败 (HTTP $code), 可能是其他服务占用。"
        fi
    else
        info "应用未在端口 $port 运行 (启动: bash scripts/run.sh)"
    fi
}

# ----------------------------------------------------------------------------
# 6. Caddy + HTTPS
# ----------------------------------------------------------------------------
check_caddy() {
    section "Caddy 与 HTTPS"
    local file="$APP_DIR/.env" enabled="no" domain="" caddyfile="/etc/caddy/Caddyfile"
    [ -f "$file" ] && enabled="$(env_get "$file" ENABLE_HTTPS)"
    [ -f "$file" ] && domain="$(env_get "$file" HJ_CADDY_DOMAIN)"

    if [ "$enabled" != "yes" ]; then
        info "HTTPS 未启用 (ENABLE_HTTPS != yes), 跳过 Caddy 检查。"
        return 0
    fi

    if ! command_exists caddy; then
        fail "HTTPS 已启用但未检测到 Caddy"
        return 1
    fi
    pass "Caddy 已安装: $(caddy version 2>/dev/null | head -n1)"

    if [ ! -f "$caddyfile" ]; then
        fail "未找到 Caddyfile: $caddyfile"
        return 1
    fi
    pass "Caddyfile 存在: $caddyfile"

    if caddy validate --config "$caddyfile" >/dev/null 2>&1; then
        pass "Caddyfile 校验通过"
    else
        fail "Caddyfile 校验失败"
    fi

    if command_exists systemctl && systemctl is-active --quiet caddy 2>/dev/null; then
        pass "Caddy 服务运行中 (systemctl is-active caddy)"
    else
        fail "Caddy 服务未运行, 尝试: sudo systemctl start caddy"
    fi

    if [ -n "$domain" ]; then
        local code
        code="$(curl -skS -o /dev/null -w '%{http_code}' --connect-timeout 6 --max-time 12 "https://$domain" 2>/dev/null || true)"
        if [ "$code" = "200" ]; then
            pass "HTTPS 可访问: https://$domain (HTTP $code)"
        else
            warn "HTTPS 响应异常: https://$domain (HTTP $code), 证书可能仍在签发中。"
        fi
    fi
}

# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
main() {
    printf '%s==============================================================\n' "$C_BOLD$C_BLUE"
    printf '   智鉴黄精 AI 品质检测系统 - 环境检查\n'
    printf '   项目目录: %s\n' "$APP_DIR"
    printf '==============================================================%s\n' "$C_RESET"

    check_python || true
    check_venv  || true
    check_env   || true
    check_network || true
    check_port  || true
    check_caddy || true
    summary
}

main "$@"
