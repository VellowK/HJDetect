#!/bin/bash
# ============================================================================
# 智鉴黄精 AI 品质检测系统 - 一键安装脚本 (Linux)
#
# 用法:
#   一键安装 (curl | bash):
#     curl -fsSL https://raw.githubusercontent.com/VellowK/HJDetect/main/scripts/install.sh | bash
#
#   本地执行:
#     bash scripts/install.sh
#
#   非交互模式 (通过环境变量传参):
#     HJ_NONINTERACTIVE=1 ARK_API_KEY=xxxx PORT=8501 HJ_HTTPS=no bash scripts/install.sh
#
# 环境变量:
#   HJ_INSTALL_DIR     安装目录 (默认 ~/hjdetect; 在仓库内执行时使用仓库根目录)
#   HJ_NONINTERACTIVE  1 = 非交互模式, 全部使用环境变量或默认值
#   HJ_HTTPS           yes / no, 是否配置 Caddy + Let's Encrypt HTTPS
#   HJ_DOMAIN          HTTPS 域名
#   HJ_EMAIL           证书邮箱
#   HJ_SYSTEMD         yes / no, 是否注册 systemd 服务
#   ARK_API_KEY / ARK_BASE_URL / ARK_MODEL / APP_MODE / HOST / PORT
# ============================================================================

set -euo pipefail

REPO_URL="https://github.com/VellowK/HJDetect"
REPO_BRANCH="main"
DEFAULT_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL="doubao-seed-2.0-lite"
DEFAULT_PORT="8501"
DEFAULT_HOST="0.0.0.0"

# ----------------------------------------------------------------------------
# 彩色输出
# ----------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_RESET=$'\033[0m'; C_RED=$'\033[0;31m'; C_GREEN=$'\033[0;32m'
    C_YELLOW=$'\033[0;33m'; C_BLUE=$'\033[0;34m'; C_BOLD=$'\033[1m'
else
    C_RESET=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_BOLD=''
fi

info() { printf '%s[INFO]%s %s\n'  "$C_BLUE"   "$C_RESET" "$*"; }
ok()   { printf '%s[ OK ]%s %s\n'  "$C_GREEN"  "$C_RESET" "$*"; }
warn() { printf '%s[WARN]%s %s\n'  "$C_YELLOW" "$C_RESET" "$*"; }
err()  { printf '%s[FAIL]%s %s\n'  "$C_RED"    "$C_RESET" "$*" >&2; }
die()  { err "$*"; exit 1; }
step() { printf '\n%s==> %s%s\n' "$C_BOLD" "$*" "$C_RESET"; }

# ----------------------------------------------------------------------------
# 交互工具: curl | bash 时 stdin 是脚本流, 交互输入走 /dev/tty
# ----------------------------------------------------------------------------
TTY_AVAILABLE=0
if [ -r /dev/tty ] && [ -w /dev/tty ]; then
    TTY_AVAILABLE=1
fi
if [ "${HJ_NONINTERACTIVE:-0}" = "1" ] || [ "$TTY_AVAILABLE" -eq 0 ]; then
    INTERACTIVE=0
else
    INTERACTIVE=1
fi

ask() {
    # ask <提示语> <默认值> -> 结果输出到 stdout (交互时提示写 /dev/tty)
    local prompt="$1" default="${2:-}" input=""
    if [ "$INTERACTIVE" -eq 0 ]; then
        printf '%s' "$default"
        return 0
    fi
    if [ -n "$default" ]; then
        printf '%s [%s]: ' "$prompt" "$default" > /dev/tty
    else
        printf '%s: ' "$prompt" > /dev/tty
    fi
    read -r input < /dev/tty || input=""
    [ -n "$input" ] || input="$default"
    printf '%s' "$input"
}

ask_secret() {
    # ask_secret <提示语> -> 隐藏输入 (read -s), 结果输出到 stdout
    local prompt="$1" input=""
    if [ "$INTERACTIVE" -eq 0 ]; then
        printf ''
        return 0
    fi
    printf '%s' "$prompt" > /dev/tty
    read -r -s input < /dev/tty || input=""
    printf '\n' > /dev/tty
    printf '%s' "$input"
}

ask_yes_no() {
    # ask_yes_no <提示语> <默认 yes|no> -> 输出 yes / no
    local prompt="$1" default="${2:-yes}" input=""
    if [ "$INTERACTIVE" -eq 0 ]; then
        printf '%s' "$default"
        return 0
    fi
    local hint="Y/n" default_text="Y"
    if [ "$default" != "yes" ]; then
        hint="y/N"; default_text="N"
    fi
    input="$(ask "$prompt ($hint)" "$default_text")"
    case "$input" in
        [Yy]|[Yy][Ee][Ss]) printf 'yes' ;;
        [Nn]|[Nn][Oo])     printf 'no' ;;
        *)                 printf '%s' "$default" ;;
    esac
}

# ----------------------------------------------------------------------------
# 通用工具
# ----------------------------------------------------------------------------
command_exists() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
require_priv() {
    if [ "$(id -u)" -eq 0 ]; then
        SUDO=""
    elif command_exists sudo; then
        SUDO="sudo"
    else
        die "需要 root 权限执行系统操作, 请以 root 运行或安装 sudo。"
    fi
}

as_root() {
    if [ -n "$SUDO" ]; then "$SUDO" "$@"; else "$@"; fi
}

os_id() {
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        printf '%s' "${ID:-unknown}"
    else
        printf 'unknown'
    fi
}

version_ge() { [ "$(printf '%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]; }

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

# ----------------------------------------------------------------------------
# 1. 系统环境检查
# ----------------------------------------------------------------------------
check_system() {
    step "检查系统环境"
    local distro
    distro="$(os_id)"
    case "$distro" in
        debian|ubuntu|linuxmint|raspbian)
            ok "检测到 Debian 系发行版: ${PRETTY_NAME:-$distro}"
            PKG_MGR="apt"
            ;;
        unknown)
            warn "无法识别发行版 (/etc/os-release 缺失), 将尝试继续。"
            PKG_MGR="none"
            ;;
        *)
            warn "检测到非 Debian 系发行版 ($distro), 脚本优先支持 Debian/Ubuntu。"
            warn "将尝试继续, 但 python3/git/caddy 需自行确保可用。"
            PKG_MGR="none"
            ;;
    esac
}

# ----------------------------------------------------------------------------
# 2. Python 3.8+
# ----------------------------------------------------------------------------
ensure_python() {
    step "检查 Python 3.8+"
    local py="" ver=""
    if command_exists python3; then
        py="python3"
    elif command_exists python && python -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' 2>/dev/null; then
        py="python"
    fi

    if [ -z "$py" ]; then
        if [ "$PKG_MGR" = "apt" ]; then
            info "未检测到 Python3, 尝试通过 apt 安装..."
            as_root apt-get update -y
            as_root apt-get install -y python3 python3-venv python3-pip
            py="python3"
        else
            die "未检测到 Python3, 请先安装 Python 3.8+ 后重试。"
        fi
    fi

    ver="$("$py" -c 'import sys; print("%d.%d" % (sys.version_info[0], sys.version_info[1]))')"
    if ! version_ge "$ver" "3.8"; then
        die "Python 版本过低 (当前 $ver), 需要 3.8+。"
    fi
    ok "Python 版本满足要求: $ver"
    PYTHON_BIN="$py"
}

# ----------------------------------------------------------------------------
# 3. Git
# ----------------------------------------------------------------------------
ensure_git() {
    step "检查 Git"
    if command_exists git; then
        ok "Git 已安装: $(git --version)"
        return 0
    fi
    if [ "$PKG_MGR" = "apt" ]; then
        info "未检测到 Git, 尝试通过 apt 安装..."
        as_root apt-get update -y
        as_root apt-get install -y git
        ok "Git 安装完成: $(git --version)"
    else
        die "未检测到 Git, 请先安装 Git 后重试。"
    fi
}

# ----------------------------------------------------------------------------
# 4. 获取代码
# ----------------------------------------------------------------------------
acquire_source() {
    step "获取项目代码"

    # 在仓库内执行时直接使用仓库根目录
    local self_dir=""
    self_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd -P || true)"
    if [ -z "${HJ_INSTALL_DIR:-}" ] && [ -n "$self_dir" ] && [ -f "$self_dir/../app.py" ]; then
        INSTALL_DIR="$(cd "$self_dir/.." && pwd -P)"
        info "检测到在仓库内执行, 使用项目目录: $INSTALL_DIR"
    fi
    if [ -z "${INSTALL_DIR:-}" ]; then
        INSTALL_DIR="$(ask "安装目录" "$HOME/hjdetect")"
    fi
    INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"
    mkdir -p "$(dirname "$INSTALL_DIR")"

    if [ -d "$INSTALL_DIR/.git" ]; then
        info "目录已存在且为 Git 仓库, 检查更新: $INSTALL_DIR"
        if git -C "$INSTALL_DIR" remote get-url origin >/dev/null 2>&1; then
            git -C "$INSTALL_DIR" fetch origin "$REPO_BRANCH" --depth 1 || warn "git fetch 失败, 使用现有代码继续。"
            if git -C "$INSTALL_DIR" diff --quiet && git -C "$INSTALL_DIR" diff --cached --quiet; then
                if git -C "$INSTALL_DIR" reset --hard "origin/$REPO_BRANCH" >/dev/null 2>&1; then
                    ok "代码已更新到最新版本。"
                else
                    warn "代码更新失败, 使用现有代码继续。"
                fi
            else
                warn "本地存在未提交修改, 跳过代码更新以保护用户改动。"
            fi
        else
            warn "远程 origin 未配置, 使用现有代码继续。"
        fi
    elif [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
        die "目录 $INSTALL_DIR 已存在且不是 Git 仓库, 请更换安装目录 (HJ_INSTALL_DIR)。"
    else
        info "克隆仓库: $REPO_URL -> $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR" \
            || die "克隆仓库失败, 请检查网络连接后重试。"
        ok "代码获取完成。"
    fi

    [ -f "$INSTALL_DIR/app.py" ] || warn "仓库中未找到 app.py, 后续启动可能失败。"
}

# ----------------------------------------------------------------------------
# 5. 虚拟环境与依赖
# ----------------------------------------------------------------------------
setup_venv() {
    step "创建 Python 虚拟环境"
    cd "$INSTALL_DIR"
    if [ -x "venv/bin/python" ]; then
        ok "虚拟环境已存在: $INSTALL_DIR/venv"
    else
        # 尝试创建虚拟环境
        if ! "$PYTHON_BIN" -m venv venv 2>/dev/null; then
            warn "venv 模块不可用，尝试自动安装 python3-venv..."
            
            # 检测系统类型并安装 python3-venv 和 python3-pip
            if command -v apt-get >/dev/null 2>&1; then
                info "检测到 Debian/Ubuntu 系统，安装 python3-venv 和 python3-pip..."
                as_root apt-get update -qq
                as_root apt-get install -y python3-venv python3-pip
            elif command -v yum >/dev/null 2>&1; then
                info "检测到 CentOS/RHEL 系统，安装 python3-venv..."
                as_root yum install -y python3-venv python3-pip
            elif command -v dnf >/dev/null 2>&1; then
                info "检测到 Fedora 系统，安装 python3-venv..."
                as_root dnf install -y python3-venv python3-pip
            else
                die "无法自动安装 python3-venv，请手动安装后重试。"
            fi
            
            # 重新尝试创建虚拟环境
            "$PYTHON_BIN" -m venv venv || die "安装 python3-venv 后仍无法创建虚拟环境。"
        fi
        ok "虚拟环境创建完成: $INSTALL_DIR/venv"
    fi
    
    # 检查虚拟环境中是否有 pip，如果没有则手动安装
    if ! ./venv/bin/python -m pip --version >/dev/null 2>&1; then
        warn "虚拟环境中没有 pip，尝试修复..."
        
        # 方法1: 尝试用 ensurepip 安装
        if ./venv/bin/python -m ensurepip --upgrade 2>/dev/null; then
            ok "已通过 ensurepip 安装 pip"
        else
            # 方法2: 如果 ensurepip 不可用，从系统安装 pip
            info "ensurepip 不可用，安装系统 python3-pip 包..."
            if command -v apt-get >/dev/null 2>&1; then
                as_root apt-get install -y python3-pip
            elif command -v yum >/dev/null 2>&1; then
                as_root yum install -y python3-pip
            elif command -v dnf >/dev/null 2>&1; then
                as_root dnf install -y python3-pip
            fi
            
            # 重新创建虚拟环境（这次会包含 pip）
            rm -rf venv
            "$PYTHON_BIN" -m venv venv || die "重新创建虚拟环境失败"
            ok "已重新创建包含 pip 的虚拟环境"
        fi
    fi

    step "安装项目依赖"
    ./venv/bin/python -m pip install --upgrade pip >/dev/null \
        || warn "pip 升级失败, 使用现有 pip 继续。"
    if [ -f requirements.txt ]; then
        info "安装 requirements.txt ..."
        ./venv/bin/python -m pip install -r requirements.txt \
            || die "依赖安装失败, 请检查网络或 requirements.txt。"
    else
        warn "未找到 requirements.txt, 安装最小依赖 (streamlit python-dotenv requests)..."
        ./venv/bin/python -m pip install streamlit python-dotenv requests \
            || die "依赖安装失败, 请检查网络连接。"
    fi
    ok "依赖安装完成。"
}

# ----------------------------------------------------------------------------
# 配置工具
# ----------------------------------------------------------------------------
single_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

strip_quotes() {
    printf '%s' "$1" | sed "s/^'//;s/'$//;s/^\"//;s/\"\$//"
}

upsert_env_line() {
    # upsert_env_line <文件> <KEY> <value>  更新或追加该键, 不触碰其他行
    local file="$1" key="$2" value="$3"
    if grep -qE "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

env_get() {
    # env_get <文件> <KEY> -> 去引号后的值
    local value=""
    value="$(grep -E "^$2=" "$1" 2>/dev/null | tail -n1 | cut -d= -f2-)"
    strip_quotes "$value"
}

# ----------------------------------------------------------------------------
# 6. 交互式配置 -> .env
# ----------------------------------------------------------------------------
configure_app() {
    step "配置应用"
    cd "$INSTALL_DIR"

    local existing_key="no" existing_url="" existing_model="" existing_mode="" \
          existing_host="" existing_port=""
    if [ -f .env ]; then
        cp -f .env ".env.bak.$(date +%Y%m%d%H%M%S)"
        existing_key="$(grep -qE '^ARK_API_KEY=.+' .env && echo yes || echo no)"
        existing_url="$(env_get .env ARK_BASE_URL)"
        existing_model="$(env_get .env ARK_MODEL)"
        existing_mode="$(env_get .env APP_MODE)"
        existing_host="$(env_get .env HOST)"
        existing_port="$(env_get .env PORT)"
        ok "检测到现有 .env, 已自动备份 (未询问到的配置保持不变)。"
    fi

    # --- API Key (隐藏输入) ---
    local api_key_value="${ARK_API_KEY:-}"
    if [ -z "$api_key_value" ]; then
        if [ "$existing_key" = "yes" ]; then
            local keep
            keep="$(ask_yes_no "已存在 API Key, 是否保留现有 Key?" "yes")"
            if [ "$keep" = "yes" ]; then
                api_key_value="__KEEP__"
            else
                api_key_value="$(ask_secret "请输入 ARK API Key (输入内容不回显): ")"
            fi
        else
            api_key_value="$(ask_secret "请输入 ARK API Key (输入内容不回显, 可留空稍后配置): ")"
        fi
    fi

    # --- API / Web 配置 ---
    local input_url input_model input_mode input_host input_port
    input_url="${ARK_BASE_URL:-}"
    [ -z "$input_url" ] && input_url="$(ask "ARK API Endpoint" "${existing_url:-$DEFAULT_BASE_URL}")"
    input_model="${ARK_MODEL:-}"
    [ -z "$input_model" ] && input_model="$(ask "模型名称" "${existing_model:-$DEFAULT_MODEL}")"
    input_mode="${APP_MODE:-}"
    [ -z "$input_mode" ] && input_mode="$(ask "运行模式 (online/demo)" "${existing_mode:-online}")"
    input_host="${HOST:-}"
    [ -z "$input_host" ] && input_host="$(ask "监听地址 (0.0.0.0 为全网可访问)" "${existing_host:-$DEFAULT_HOST}")"
    input_port="${PORT:-}"
    [ -z "$input_port" ] && input_port="$(ask "监听端口" "${existing_port:-$DEFAULT_PORT}")"

    case "$input_mode" in online|demo) ;; *) input_mode="online" ;; esac
    if ! printf '%s' "$input_port" | grep -qE '^[0-9]+$' || [ "$input_port" -lt 1 ] || [ "$input_port" -gt 65535 ]; then
        warn "端口无效, 回退为 $DEFAULT_PORT。"
        input_port="$DEFAULT_PORT"
    fi

    # --- 写入 .env (值用单引号包裹; API Key 保留原值时不动该行) ---
    umask 077
    touch .env
    if [ "$api_key_value" != "__KEEP__" ]; then
        upsert_env_line .env ARK_API_KEY "$(single_quote "$api_key_value")"
    fi
    upsert_env_line .env ARK_BASE_URL "$(single_quote "$input_url")"
    upsert_env_line .env ARK_MODEL "$(single_quote "$input_model")"
    upsert_env_line .env APP_MODE "$(single_quote "$input_mode")"
    upsert_env_line .env HOST "$(single_quote "$input_host")"
    upsert_env_line .env PORT "$(single_quote "$input_port")"
    chmod 600 .env
    umask 022

    HOST_VALUE="$input_host"
    PORT_VALUE="$input_port"
    ok ".env 配置已写入: $INSTALL_DIR/.env (权限 600)"
}

# ----------------------------------------------------------------------------
# 7. HTTPS (Caddy + Let's Encrypt)
# ----------------------------------------------------------------------------
install_caddy() {
    if command_exists caddy; then
        ok "Caddy 已安装: $(caddy version)"
        return 0
    fi
    if [ "$PKG_MGR" != "apt" ]; then
        warn "当前发行版不支持自动安装 Caddy, 请参考 https://caddyserver.com/docs/install 手动安装后重跑本脚本。"
        return 1
    fi
    info "安装 Caddy (官方 APT 源)..."
    as_root apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl \
        || die "安装 Caddy 前置依赖失败。"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | as_root gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
        || die "下载 Caddy GPG key 失败。"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | as_root tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null \
        || die "写入 Caddy APT 源失败。"
    as_root apt-get update -y
    as_root apt-get install -y caddy || die "Caddy 安装失败。"
    ok "Caddy 安装完成: $(caddy version)"
}

configure_https() {
    step "HTTPS 配置 (Caddy + Let's Encrypt)"
    cd "$INSTALL_DIR"

    local existing_domain="" existing_email=""
    if [ -f .env ]; then
        existing_domain="$(env_get .env HJ_CADDY_DOMAIN)"
        existing_email="$(env_get .env HJ_CADDY_EMAIL)"
    fi

    if [ -z "${HTTPS_WANT:-}" ]; then
        HTTPS_WANT="$(ask_yes_no "是否配置 HTTPS (需要公网域名解析到本机)?" "no")"
    fi
    if [ "$HTTPS_WANT" != "yes" ]; then
        upsert_env_line .env ENABLE_HTTPS "'no'"
        info "跳过 HTTPS 配置。"
        return 0
    fi

    if [ -z "$HJ_DOMAIN" ]; then
        HJ_DOMAIN="$(ask "域名 (例如 detect.example.com)" "$existing_domain")"
    fi
    if [ -z "$HJ_DOMAIN" ]; then
        warn "未提供域名, 跳过 HTTPS 配置。"
        upsert_env_line .env ENABLE_HTTPS "'no'"
        return 0
    fi
    if [ -z "$HJ_EMAIL" ]; then
        HJ_EMAIL="$(ask "证书邮箱 (Let's Encrypt 通知)" "$existing_email")"
    fi

    # DNS 检查
    if command_exists getent && ! getent hosts "$HJ_DOMAIN" >/dev/null 2>&1; then
        warn "域名 $HJ_DOMAIN 当前无法解析, Let's Encrypt 签发将失败, 仍会继续写配置。"
    else
        ok "域名解析检查通过: $HJ_DOMAIN"
    fi

    if port_listening 80 || port_listening 443; then
        warn "本机 80/443 端口已被占用 (可能是现有 Caddy/Nginx), 证书签发可能受影响。"
    fi

    if ! install_caddy; then
        upsert_env_line .env ENABLE_HTTPS "'no'"
        return 0
    fi

    local caddyfile="/etc/caddy/Caddyfile"
    as_root mkdir -p /etc/caddy
    if [ -f "$caddyfile" ]; then
        as_root cp -f "$caddyfile" "/etc/caddy/Caddyfile.bak.$(date +%Y%m%d%H%M%S)"
        info "已备份现有 Caddyfile。"
    fi
    {
        printf '%s {\n' "$HJ_DOMAIN"
        if [ -n "$HJ_EMAIL" ]; then
            printf '    tls %s\n' "$HJ_EMAIL"
        fi
        printf '    reverse_proxy 127.0.0.1:%s\n' "$PORT_VALUE"
        printf '}\n'
    } | as_root tee "$caddyfile" > /dev/null

    as_root caddy validate --config "$caddyfile" || die "Caddyfile 校验失败。"
    if command_exists systemctl; then
        as_root systemctl enable --now caddy || warn "caddy 服务启动失败, 请检查: systemctl status caddy"
        as_root systemctl reload caddy 2>/dev/null || as_root systemctl restart caddy || true
    fi
    ok "Caddy 反向代理已配置: https://$HJ_DOMAIN -> 127.0.0.1:$PORT_VALUE"
    ok "证书由 Caddy 自动申请并续期 (Let's Encrypt)。"

    upsert_env_line .env ENABLE_HTTPS "'yes'"
    upsert_env_line .env HJ_CADDY_DOMAIN "$(single_quote "$HJ_DOMAIN")"
    if [ -n "$HJ_EMAIL" ]; then
        upsert_env_line .env HJ_CADDY_EMAIL "$(single_quote "$HJ_EMAIL")"
    fi
}

# ----------------------------------------------------------------------------
# 8. systemd 服务 (可选)
# ----------------------------------------------------------------------------
configure_systemd() {
    step "systemd 服务 (可选)"
    if ! command_exists systemctl; then
        info "系统无 systemd, 跳过。"
        return 0
    fi
    if [ -z "${HJ_SYSTEMD_WANT:-}" ]; then
        HJ_SYSTEMD_WANT="$(ask_yes_no "是否注册 systemd 开机自启服务 (huangjing)?" "no")"
    fi
    if [ "$HJ_SYSTEMD_WANT" != "yes" ]; then
        info "跳过 systemd 配置。"
        return 0
    fi

    local run_user
    run_user="$(logname 2>/dev/null || printf '%s' "${SUDO_USER:-$(id -un)}")"
    local unit="/etc/systemd/system/huangjing.service"
    {
        printf '[Unit]\n'
        printf 'Description=HJDetect - AI Huangjing Quality Detection\n'
        printf 'After=network.target\n\n'
        printf '[Service]\n'
        printf 'Type=simple\n'
        printf 'User=%s\n' "$run_user"
        printf 'WorkingDirectory=%s\n' "$INSTALL_DIR"
        printf 'ExecStart=%s/venv/bin/python -m streamlit run app.py --server.address %s --server.port %s\n' \
            "$INSTALL_DIR" "$HOST_VALUE" "$PORT_VALUE"
        printf 'Restart=on-failure\n'
        printf 'RestartSec=5\n\n'
        printf '[Install]\n'
        printf 'WantedBy=multi-user.target\n'
    } | as_root tee "$unit" > /dev/null
    as_root systemctl daemon-reload
    as_root systemctl enable --now huangjing || warn "huangjing 服务启动失败, 请检查: systemctl status huangjing"
    ok "systemd 服务已注册: huangjing (start/stop/restart/status)"
}

# ----------------------------------------------------------------------------
# 9. 健康检查
# ----------------------------------------------------------------------------
health_check() {
    step "健康检查"
    local url="http://127.0.0.1:${PORT_VALUE}/_stcore/health" i=0 pid=""
    mkdir -p "$INSTALL_DIR/logs"

    info "临时启动应用进行健康检查 (最多等待 60 秒)..."
    (
        cd "$INSTALL_DIR"
        nohup ./venv/bin/python -m streamlit run app.py \
            --server.address "$HOST_VALUE" --server.port "$PORT_VALUE" \
            --server.headless true \
            > "$INSTALL_DIR/logs/health-check.log" 2>&1 &
        echo $! > "$INSTALL_DIR/logs/health-check.pid"
    )

    pid="$(cat "$INSTALL_DIR/logs/health-check.pid" 2>/dev/null || true)"
    while [ "$i" -lt 30 ]; do
        if curl -fsS --connect-timeout 2 --max-time 4 "$url" 2>/dev/null | grep -q 'ok'; then
            ok "健康检查通过: $url"
            if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; fi
            sleep 1
            rm -f "$INSTALL_DIR/logs/health-check.pid"
            return 0
        fi
        i=$((i + 1))
        sleep 2
    done

    warn "健康检查未通过, 请查看日志: $INSTALL_DIR/logs/health-check.log"
    if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; fi
    rm -f "$INSTALL_DIR/logs/health-check.pid"
    return 1
}

# ----------------------------------------------------------------------------
# 10. 安装汇总
# ----------------------------------------------------------------------------
print_summary() {
    printf '\n'
    printf '%s==============================================================%s\n' "$C_GREEN" "$C_RESET"
    printf '%s  智鉴黄精 AI 品质检测系统 安装完成%s\n' "$C_BOLD" "$C_RESET"
    printf '%s==============================================================%s\n' "$C_GREEN" "$C_RESET"
    printf '  安装目录 : %s\n' "$INSTALL_DIR"
    printf '  监听地址 : %s:%s\n' "$HOST_VALUE" "$PORT_VALUE"
    if [ "${HTTPS_WANT:-no}" = "yes" ] && [ -n "${HJ_DOMAIN:-}" ]; then
        printf '  HTTPS    : https://%s\n' "$HJ_DOMAIN"
    fi
    printf '\n'
    printf '  启动服务 : cd %s && bash scripts/run.sh\n' "$INSTALL_DIR"
    printf '  环境检查 : cd %s && bash scripts/check.sh\n' "$INSTALL_DIR"
    printf '%s==============================================================%s\n' "$C_GREEN" "$C_RESET"
}

# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
do_install() {
    printf '%s==============================================================\n' "$C_BOLD$C_BLUE"
    printf '   智鉴黄精 AI 品质检测系统 - 安装\n'
    printf '==============================================================%s\n' "$C_RESET"

    check_system
    require_priv
    ensure_python
    ensure_git
    acquire_source
    setup_venv
    configure_app
    configure_https
    configure_systemd
    if ! health_check; then
        warn "健康检查未通过, 可修复配置后运行 bash scripts/check.sh 排查。"
    fi
    print_summary
}

do_uninstall() {
    printf '%s==============================================================\n' "$C_BOLD$C_RED"
    printf '   智鉴黄精 AI 品质检测系统 - 卸载\n'
    printf '==============================================================%s\n' "$C_RESET"
    
    local install_dir="${HJ_INSTALL_DIR:-$HOME/hjdetect}"
    
    if [ ! -d "$install_dir" ]; then
        warn "未找到安装目录: $install_dir"
        return 0
    fi
    
    info "将要卸载: $install_dir"
    
    if [ "${HJ_NONINTERACTIVE:-0}" != "1" ]; then
        printf "确认卸载吗？这将删除所有数据 [y/N]: "
        read -r confirm < /dev/tty || confirm="n"
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            info "取消卸载。"
            return 0
        fi
    fi
    
    # 停止并删除systemd服务
    if [ -f /etc/systemd/system/huangjing.service ]; then
        info "停止并移除 systemd 服务..."
        as_root systemctl stop huangjing 2>/dev/null || true
        as_root systemctl disable huangjing 2>/dev/null || true
        as_root rm -f /etc/systemd/system/huangjing.service
        as_root systemctl daemon-reload
        ok "systemd 服务已移除"
    fi
    
    # 删除安装目录
    info "删除安装目录: $install_dir"
    rm -rf "$install_dir"
    ok "卸载完成"
}

do_update() {
    printf '%s==============================================================\n' "$C_BOLD$C_YELLOW"
    printf '   智鉴黄精 AI 品质检测系统 - 更新\n'
    printf '==============================================================%s\n' "$C_RESET"
    
    local install_dir="${HJ_INSTALL_DIR:-$HOME/hjdetect}"
    
    if [ ! -d "$install_dir" ]; then
        die "未找到安装目录: $install_dir，请先执行安装。"
    fi
    
    cd "$install_dir"
    
    if [ ! -d .git ]; then
        die "$install_dir 不是 git 仓库，无法更新。"
    fi
    
    info "拉取最新代码..."
    git fetch origin
    git reset --hard origin/main
    ok "代码已更新到最新版本"
    
    info "更新依赖..."
    ./venv/bin/python -m pip install --upgrade pip -q
    ./venv/bin/python -m pip install -r requirements.txt -q
    ok "依赖已更新"
    
    # 重启服务
    if systemctl is-active --quiet huangjing 2>/dev/null; then
        info "重启服务..."
        as_root systemctl restart huangjing
        ok "服务已重启"
    else
        info "服务未运行，跳过重启。"
    fi
    
    ok "更新完成！"
}

do_check() {
    printf '%s==============================================================\n' "$C_BOLD$C_GREEN"
    printf '   智鉴黄精 AI 品质检测系统 - 环境检查\n'
    printf '==============================================================%s\n' "$C_RESET"
    
    local install_dir="${HJ_INSTALL_DIR:-$HOME/hjdetect}"
    
    if [ ! -d "$install_dir" ]; then
        die "未找到安装目录: $install_dir，请先执行安装。"
    fi
    
    if [ -f "$install_dir/scripts/check.sh" ]; then
        bash "$install_dir/scripts/check.sh"
    else
        die "未找到检查脚本: $install_dir/scripts/check.sh"
    fi
}

do_version() {
    printf '%s==============================================================\n' "$C_BOLD$C_BLUE"
    printf '   智鉴黄精 AI 品质检测系统 - 版本信息\n'
    printf '==============================================================%s\n' "$C_RESET"
    
    local install_dir="${HJ_INSTALL_DIR:-$HOME/hjdetect}"
    
    # 检查是否已安装
    if [ ! -d "$install_dir" ]; then
        warn "未找到安装目录: $install_dir"
        info "系统未安装"
        return 0
    fi
    
    printf '\n'
    
    # 读取本地版本
    if [ -f "$install_dir/VERSION" ]; then
        local_version=$(cat "$install_dir/VERSION" 2>/dev/null | tr -d '[:space:]')
        printf "  本地版本 : %s%s%s\n" "$C_GREEN" "$local_version" "$C_RESET"
    else
        printf "  本地版本 : %s未知%s\n" "$C_YELLOW" "$C_RESET"
        local_version="unknown"
    fi
    
    # 读取Git信息
    if [ -d "$install_dir/.git" ]; then
        cd "$install_dir"
        local git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        local git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        local git_date=$(git log -1 --format=%cd --date=short 2>/dev/null || echo "unknown")
        
        printf "  Git 分支 : %s\n" "$git_branch"
        printf "  Git 提交 : %s\n" "$git_commit"
        printf "  提交日期 : %s\n" "$git_date"
    fi
    
    # 检查远程最新版本
    printf '\n'
    info "检查远程最新版本..."
    
    if command -v curl >/dev/null 2>&1; then
        remote_version=$(curl -fsSL --connect-timeout 5 \
            "https://raw.githubusercontent.com/VellowK/HJDetect/main/VERSION" 2>/dev/null | tr -d '[:space:]')
        
        if [ -n "$remote_version" ]; then
            printf "  远程版本 : %s%s%s\n" "$C_BLUE" "$remote_version" "$C_RESET"
            
            # 比较版本
            if [ "$local_version" = "$remote_version" ]; then
                ok "已是最新版本"
            elif [ "$local_version" = "unknown" ]; then
                warn "无法确定本地版本"
            else
                warn "发现新版本：$remote_version (当前: $local_version)"
                info "运行 '更新系统' 升级到最新版本"
            fi
        else
            warn "无法获取远程版本信息（网络问题或仓库不可达）"
        fi
    else
        warn "未安装 curl，无法检查远程版本"
    fi
    
    printf '\n'
}

show_menu() {
    printf '\n%s==============================================================\n' "$C_BOLD$C_BLUE"
    printf '   智鉴黄精 AI 品质检测系统 - 管理脚本\n'
    printf '==============================================================%s\n' "$C_RESET"
    printf '\n'
    printf '  1) 安装系统\n'
    printf '  2) 卸载系统\n'
    printf '  3) 更新系统\n'
    printf '  4) 环境检查\n'
    printf '  5) 版本信息\n'
    printf '  6) 退出\n'
    printf '\n'
}
    printf '  3) 更新系统\n'
    printf '  4) 环境检查\n'
    printf '  5) 退出\n'
    printf '\n'
}

main() {
    # 如果是非交互模式（环境变量指定），直接安装
    if [ "${HJ_NONINTERACTIVE:-0}" = "1" ]; then
        do_install
        return
    fi
    
    # 如果有参数，根据参数执行
    if [ $# -gt 0 ]; then
        case "$1" in
            install|--install|-i)
                do_install
                ;;
            uninstall|--uninstall|-u)
                do_uninstall
                ;;
            update|--update|-U)
                do_update
                ;;
            check|--check|-c)
                do_check
                ;;
            version|--version|-v)
                do_version
                ;;
            *)
                echo "未知选项: $1"
                echo "用法: $0 [install|uninstall|update|check|version]"
                exit 1
                ;;
        esac
        return
    fi
    
    # 交互式菜单
    while true; do
        show_menu
        printf "请选择操作 [1-6]: "
        read -r choice < /dev/tty
        
        case "$choice" in
            1)
                do_install
                break
                ;;
            2)
                do_uninstall
                break
                ;;
            3)
                do_update
                break
                ;;
            4)
                do_check
                ;;
            5)
                do_version
                ;;
            6|q|Q)
                info "退出。"
                exit 0
                ;;
            *)
                warn "无效选择，请输入 1-6"
                ;;
        esac
    done
}

main "$@"
