# 安装脚本缓存问题解决方案

## 问题说明

GitHub代理 `https://v4.gh-proxy.org/` 缓存了旧版本的安装脚本，导致配置顺序和bug修复没有生效。

最新版本提交: `ac9614a` (2024-03-09)

---

## 解决方案

### 方案1：直接Git克隆（推荐，最可靠）

```bash
# 删除旧的安装（如果有）
rm -rf /root/hjdetect

# 克隆最新代码
git clone https://github.com/VellowK/HJDetect.git /root/hjdetect
cd /root/hjdetect

# 验证版本
head -5 scripts/install.sh | grep Version
# 应该看到: # Version: 1.0.1 或更新

# 运行安装脚本
bash scripts/install.sh
```

### 方案2：直接下载脚本（避开代理）

```bash
# 下载到临时文件
wget -O /tmp/install_hjdetect.sh https://raw.githubusercontent.com/VellowK/HJDetect/main/scripts/install.sh

# 验证版本
head -5 /tmp/install_hjdetect.sh | grep Version

# 运行
bash /tmp/install_hjdetect.sh
```

### 方案3：添加时间戳绕过缓存

```bash
# 添加随机参数强制刷新
curl -fsSL "https://raw.githubusercontent.com/VellowK/HJDetect/main/scripts/install.sh?t=$(date +%s)" | bash
```

### 方案4：手动安装（完全控制）

```bash
# 1. 克隆仓库
cd /root
git clone https://github.com/VellowK/HJDetect.git hjdetect
cd hjdetect

# 2. 安装 Python 环境
apt update
apt install -y python3 python3-pip python3.11-venv git curl

# 3. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 4. 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 5. 配置 .env
cp .env.example .env
nano .env
# 编辑以下内容：
# ARK_API_KEY='你的API_Key'
# ARK_BASE_URL='https://ark.cn-beijing.volces.com/api/v3'
# ARK_MODEL='ep-20241208101633-8hs2c'
# APP_MODE='online'
# HOST='0.0.0.0'
# PORT='8501'

# 保存后设置权限
chmod 600 .env

# 6. 启动服务
streamlit run app.py --server.address=0.0.0.0 --server.port=8501
```

---

## 验证安装脚本版本

运行以下命令检查脚本版本：

```bash
head -10 scripts/install.sh | grep -E "Version:|配置顺序"
```

**正确的输出应该包含**：
```
# Version: 1.0.1 (2024-03-09 语法修复版)
    # --- 配置顺序：API Key → Base URL → 模型 → 运行模式 → 监听地址 → 端口 ---
```

---

## 修复内容确认

### 1. unbound variable 错误已修复
- `${HJ_DOMAIN:-}` 和 `${HJ_EMAIL:-}` 使用默认值语法
- 兼容 `set -u` 严格模式

### 2. 配置顺序已优化
```
旧顺序: API Key → Endpoint → 模型 → 运行模式 → 监听地址 → 端口
新顺序: API Key → Base URL → 模型 → 运行模式 → 监听地址 → 端口
```

实际上顺序没变，只是添加了清晰的注释说明每一步的作用。

---

## 推荐流程

**最快最稳定的方法是方案1（Git克隆）**：

```bash
git clone https://github.com/VellowK/HJDetect.git /root/hjdetect
cd /root/hjdetect
bash scripts/install.sh
```

选择菜单中的 **1) 安装系统**，然后按提示配置：

1. API Key (隐藏输入)
2. API Base URL (默认火山引擎地址)
3. 模型名称 (默认 ep-20241208101633-8hs2c)
4. 运行模式 (online)
5. 监听地址 (0.0.0.0)
6. 监听端口 (8501)
7. 是否配置 HTTPS (可选)
8. 是否注册 systemd 服务 (可选)

---

## 安装后验证

```bash
# 检查服务状态
curl http://localhost:8501/_stcore/health

# 应该返回: {"status": "ok"}

# 如果配置了 systemd
systemctl status huangjing

# 查看日志
tail -f /root/hjdetect/logs/app.log
```

---

## 常见问题

### Q: 为什么代理的脚本是旧的？
A: CDN/代理缓存需要时间刷新，建议直接Git克隆避开缓存。

### Q: 配置顺序真的改了吗？
A: 逻辑顺序没变，但添加了清晰的注释说明每一步的用途。主要修复是 unbound variable 错误。

### Q: 怎么确认是最新版本？
A: 运行 `git log -1 --oneline` 应该看到 `ac9614a fix: 修复配置交互问题`

---

**推荐直接使用方案1（Git克隆），避开所有缓存问题！** 🎯
