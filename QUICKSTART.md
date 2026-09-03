# 快速启动指南

本指南帮助你在5分钟内启动智鉴黄精AI品质检测系统。

---

## 方式一: 一键安装（推荐）

### Linux / macOS

```bash
# 1. 进入项目目录
cd guochuang

# 2. 运行安装脚本（会自动创建虚拟环境、安装依赖、配置API Key）
bash scripts/install.sh

# 3. 启动服务
bash scripts/run.sh
```

### Windows

```batch
# 1. 进入项目目录
cd guochuang

# 2. 双击运行 install.bat（会自动创建虚拟环境、安装依赖、配置API Key）
install.bat

# 3. 双击运行 run.bat
run.bat
```

---

## 方式二: 手动安装

### 第1步: 创建虚拟环境

**Linux / macOS**:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows**:
```batch
python -m venv .venv
.venv\Scripts\activate
```

### 第2步: 安装依赖

```bash
pip install -r requirements.txt
```

### 第3步: 配置环境变量

**Linux / macOS**:
```bash
cp .env.example .env
```

**Windows**:
```batch
copy .env.example .env
```

编辑 `.env` 文件，填入你的火山引擎API Key:

```ini
# 必填: 火山引擎方舟 API Key
ARK_API_KEY=你的真实APIKey

# 可选: API地址（默认值通常不需要修改）
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 可选: 模型名称（默认值通常不需要修改）
ARK_MODEL=doubao-seed-2.0-lite

# 可选: 运行模式 (online=真实检测, demo=演示模式)
APP_MODE=online

# 可选: Web服务配置
HOST=0.0.0.0
PORT=8501

# 可选: 日志级别
LOG_LEVEL=INFO
```

### 第4步: 启动服务

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

或者使用启动脚本:

**Linux / macOS**:
```bash
bash scripts/run.sh
```

**Windows**:
```batch
run.bat
```

### 第5步: 访问系统

打开浏览器访问: **http://localhost:8501**

---

## 获取火山引擎API Key

1. 访问 [火山引擎控制台](https://console.volcengine.com/)
2. 注册/登录账号
3. 进入"方舟"(ARK)服务
4. 创建API Key
5. 确保开启了`doubao-seed-2.0-lite`模型的访问权限
6. 复制API Key到`.env`文件的`ARK_API_KEY`字段

---

## 演示模式（无需API Key）

如果暂时没有API Key，可以使用演示模式体验系统流程:

1. 编辑`.env`文件:
   ```ini
   APP_MODE=demo
   ```

2. 启动服务（演示模式会使用预设结果，不调用真实API）

---

## 使用CLI管理工具（可选）

安装后可以使用`huangjing`命令管理服务:

```bash
# Linux / macOS
./scripts/huangjing start    # 启动服务
./scripts/huangjing stop     # 停止服务
./scripts/huangjing restart  # 重启服务
./scripts/huangjing status   # 查看状态
./scripts/huangjing config   # 查看配置

# Windows
scripts\huangjing.bat start
scripts\huangjing.bat stop
scripts\huangjing.bat restart
scripts\huangjing.bat status
scripts\huangjing.bat config
```

---

## 常见问题

### 问题1: 提示"找不到模块streamlit"

**解决**: 确保已激活虚拟环境并安装依赖
```bash
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 问题2: 提示"API Key无效"

**解决**: 检查`.env`文件中的`ARK_API_KEY`是否正确，确保没有多余空格或引号

### 问题3: 端口8501已被占用

**解决**: 修改`.env`文件中的`PORT`为其他端口（如8502），然后访问 http://localhost:8502

### 问题4: 检测一直超时

**解决**: 
1. 检查网络连接是否正常
2. 检查`ARK_BASE_URL`配置是否正确
3. 检查火山引擎控制台是否开启了模型访问权限
4. 尝试切换到演示模式测试系统是否正常

---

## 下一步

- 📖 查看完整文档: [README.md](README.md)
- 🔧 查看配置说明: [.env.example](.env.example)
- 📝 查看代码审核报告: [CODE_REVIEW.md](CODE_REVIEW.md)
- 📋 查看版本历史: [CHANGELOG.md](CHANGELOG.md)
- 📚 查看技术规格: [zhijian_huangjing_technical_spec_v1.0.md](zhijian_huangjing_technical_spec_v1.0.md)

---

**祝使用愉快！** 🌿
