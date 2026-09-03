# 智鉴黄精——AI黄精品质检测系统
## 程序端技术规格与 Vibe Coding 开发需求 v1.0

> 面向校赛 MVP 的开发规格。
>
> 当前阶段使用 **Doubao-Seed-2.0-lite** 作为视觉分析模型，不训练 ResNet18。
> 后续正式版本再使用基于真实黄精数据集训练的 ResNet18 替换当前视觉模型。

---

# 1. 项目目标

开发一个用于**九蒸九晒黄精成品外观品质辅助评价**的原型系统。

系统基本流程：

```text
用户上传图片
    ↓
输入有效性判断
    ↓
Doubao-Seed-2.0-lite 视觉分析
    ↓
三个独立品质指标
    ├── 根茎完整度
    ├── 色泽均匀度
    └── 霉变风险
    ↓
程序端执行最终判定规则
    ↓
合格 / 建议人工复核 / 不合格
    ↓
结果展示
```

核心原则：

- 当前版本优先保证稳定、可演示、易部署。
- 不训练真实 ResNet18。
- 不伪造真实模型实验指标。
- Doubao-Seed-2.0-lite 负责视觉判断。
- 程序负责输入校验、模型调用、结构化结果校验、最终业务规则和界面展示。
- 未来替换 ResNet18 时，不应重写前端和业务逻辑。

# 2. 当前评价对象

评价对象：

> **九蒸九晒工艺完成后的黄精成品。**

基本评价单位：

> 图片中的一个能够被独立观察的单根黄精主体。

图片不要求只能包含一根黄精。

## 有效情况

以下情况可以继续检测：

- 单根黄精清晰展示。
- 多根黄精同时存在，但其中有一根可以明确作为主要评价对象。
- 多根轻微接触，但目标黄精仍可独立观察。
- 目标黄精主体基本完整，没有严重遮挡。

## 无效情况

以下情况应返回 `sample_valid=false`：

- 图片中不存在可识别黄精主体。
- 无法找到可独立评价的单根黄精。
- 多根黄精严重堆叠、无法区分主体。
- 目标黄精严重遮挡。
- 主体严重缺失。
- 图片严重模糊、过暗、过曝，无法可靠判断。

注意：

> `sample_valid=false` 表示输入不满足可靠评价条件，不代表黄精品质不合格。

此时：

```text
overall = 无法评价
```

# 3. 图片输入规范

支持：

- JPG
- JPEG
- PNG

建议最大文件大小：**10 MB**。

建议最低分辨率：**短边 ≥ 720 px**。

系统不强制背景颜色，但建议：

- 浅色
- 纯色
- 低纹理
- 与黄精主体存在明显颜色差异

校赛演示优先准备浅色、干净背景的黄精图片。

推荐单视角拍摄，尽量使目标黄精主体清晰可见。

# 4. 三个核心评价指标

三个指标必须**完全独立判断**。一个指标不得自动修改另一个指标。

## 4.1 根茎完整度

评价黄精主体结构的连续性和完整程度。

重点观察：

- 主体是否连续
- 是否存在明显断裂
- 是否存在明显缺失或缺口
- 是否存在明显影响整体结构的破损

以下情况本身不代表完整度低：

- 天然弯曲
- 节状膨大
- 粗细不均
- 正常表面纹理

不再使用“碎片”作为独立判断因素。

三档：

- **高**：主体结构基本完整，无明显断裂或明显缺失。
- **中**：存在局部破损、缺口或轻微结构异常，但主体仍基本保持。
- **低**：存在明显断裂、缺失或较严重结构破坏。

## 4.2 色泽均匀度

评价**同一根黄精内部的色泽分布是否协调**。

重点观察：

- 局部色差
- 色泽变化是否自然连续
- 是否存在明显异常色块
- 是否存在明显斑驳或突兀颜色变化

**绝对颜色深浅不能直接决定等级。**

三档：

- **高**：整体色泽较均匀，变化自然。
- **中**：存在一定局部色差，但整体仍较协调。
- **低**：存在明显或较大范围的异常色差、斑驳或突兀色块。

## 4.3 霉变风险

评价图片中是否存在：

> **疑似霉变相关的外观异常特征。**

综合关注：

- 局部异常颜色
- 局部异常纹理
- 异常区域连续性
- 异常区域面积
- 异常区域形态

不得因为某个区域颜色较深就直接判定为高风险。

三档：

- **低风险**：未发现明显疑似霉变相关异常特征。
- **中风险**：发现局部异常，但无法可靠区分普通色差与疑似霉变，建议人工复核。
- **高风险**：存在较明显的颜色、纹理及区域形态异常组合，具有较高疑似霉变风险。

霉变风险属于**图像外观风险筛查结果**，不得宣传为实验室级霉菌检测或绝对确认。

# 5. 指标独立原则

三个指标完全独立：

```text
根茎完整度 → 只判断结构
色泽均匀度 → 只判断色泽分布
霉变风险   → 只判断疑似异常/霉变风险
```

例如：

- 完整度低不能自动导致色泽低。
- 色泽低不能自动导致霉变高。
- 霉变高不能自动导致完整度低。

# 6. 最终综合判定

系统**不做 0～100 综合评分**。

最终结果：

```text
PASS   = 合格
REVIEW = 建议人工复核
REJECT = 不合格
INVALID = 无法评价
```

判定优先级：

1. `sample_valid=false` → `INVALID / 无法评价`
2. `mold_risk=高风险` → `REJECT / 不合格`
3. `mold_risk=中风险` → `REVIEW / 建议人工复核`
4. `completeness=低` → `REJECT / 不合格`
5. `color_uniformity=低` → `REJECT / 不合格`
6. 其他情况 → `PASS / 合格`

`REVIEW` 是风险处置状态，不是品质等级。

# 7. 视觉模型

当前模型：

> `Doubao-Seed-2.0-lite`

调用方式：

> **单张图片 + 一次模型调用 + 一次返回三个指标。**

模型负责：

- 有效样本判断
- 根茎完整度
- 色泽均匀度
- 霉变风险
- 简短视觉依据
- 异常区域文字描述

程序负责：

- 输入校验
- API 调用
- 返回数据解析
- 枚举值校验
- 最终综合判定
- UI 展示

# 8. Prompt 与 Few-shot

Prompt 独立存储，不硬编码到 `app.py`：

```text
prompts/
├── system.txt
└── references/
```

固定 Few-shot，不做动态检索。

参考样本用于帮助模型理解高/中/低定义，不等同于正式训练数据集或行业标准数据集。

# 9. 模型输出 Schema

模型严格返回合法 JSON：

```json
{
  "sample_valid": true,
  "completeness": "高",
  "color_uniformity": "中",
  "mold_risk": "低风险",
  "overall": "合格",
  "reason": "主体结构基本完整，色泽存在一定局部差异，未发现明显疑似霉变异常。",
  "anomaly_description": ""
}
```

允许值：

- `sample_valid`: `true` / `false`
- `completeness`: `高` / `中` / `低` / `null`
- `color_uniformity`: `高` / `中` / `低` / `null`
- `mold_risk`: `低风险` / `中风险` / `高风险` / `null`
- `overall`: `合格` / `建议人工复核` / `不合格` / `无法评价`

注意：

> **程序不得直接信任模型的 `overall`，必须使用前三项指标重新执行最终判定规则。**

`reason` 为一句或两句简短视觉依据；`anomaly_description` 描述异常的大致位置与表现。

当前版本不强制返回像素级 Mask 或坐标框。

# 10. 无效样本 Schema

```json
{
  "sample_valid": false,
  "completeness": null,
  "color_uniformity": null,
  "mold_risk": null,
  "overall": "无法评价",
  "reason": "未检测到能够进行可靠分析的有效黄精主体。",
  "anomaly_description": ""
}
```

`sample_valid=false` 不代表黄精品质不合格。

# 11. 程序架构

推荐技术栈：

> **Python + Streamlit**

当前不使用 Vue、FastAPI、MySQL、Redis、MQ、Kubernetes 等复杂组件。

推荐目录：

```text
huangjing-quality/
│
├── app.py
├── requirements.txt
├── .env.example
├── README.md
├── .gitignore
│
├── core/
│   ├── analyzer.py
│   ├── evaluator.py
│   ├── parser.py
│   └── validator.py
│
├── prompts/
│   ├── system.txt
│   └── references/
│
├── assets/
│   └── demo_images/
│
├── logs/
│   └── .gitkeep
│
└── scripts/
    ├── install.sh
    ├── run.sh
    ├── check.sh
    ├── install.bat
    ├── run.bat
    └── check.bat
```

# 12. 模型适配层

不要让 `app.py` 直接依赖具体模型。

定义统一视觉分析接口，例如：

```python
class VisionModel:
    def analyze(self, image):
        raise NotImplementedError
```

当前：

```text
VisionModel
    ↓
DoubaoSeedModel
```

未来：

```text
VisionModel
    ↓
ResNet18Model
```

目标：替换模型实现时，不修改 UI 和业务规则。

# 13. API 容错

## 超时

单次请求建议 30 秒超时。

## 自动重试

最多自动重试 2 次，即首次请求 + 最多 2 次重试。

以下确定性错误不应重试：

- API Key 无效
- 参数错误
- 权限错误
- 模型名称错误

## JSON 解析错误

处理顺序：

```text
模型响应
 ↓
JSON 解析
 ↓
失败
 ↓
尝试一次轻量 JSON 提取/修复
 ↓
仍失败
 ↓
返回用户友好错误
```

# 14. 页面要求

采用一页式 Streamlit 页面：

```text
标题
↓
图片上传
↓
图片预览
↓
开始检测
↓
检测结果
↓
三个独立指标
↓
综合评价
↓
检测依据
↓
最近检测记录
```

前台禁止显示：

- AI 在线
- Demo 模式
- Doubao
- Seed 2.0
- API
- Prompt
- Mock
- 模型调用
- API Key

后台可记录技术状态。

# 15. 检测结果展示

三个指标分别展示：

```text
根茎完整度：高
色泽均匀度：中
霉变风险：低风险
```

最终展示：

```text
综合评价：合格
```

或者：

```text
综合评价：建议人工复核
```

或者：

```text
综合评价：不合格
```

附简短：

> **检测依据**

# 16. REVIEW 处理

`REVIEW` 表示建议人工复核，不是第三种品质等级。

V0.1：

- 不允许直接修改模型结果。
- 不提供人工确认按钮。
- 不提供人工重新打标签功能。

未来可扩展：

```text
AI初筛
 ↓
人工复核
 ↓
专家修正
 ↓
形成训练数据
 ↓
模型迭代
```

# 17. 历史记录

不使用数据库。

当前会话保留：

> **最近 20 条检测记录**

记录：

- 检测时间
- 当前图片临时引用
- 三个指标
- 最终处置状态
- reason
- anomaly_description

默认不永久保存用户图片；程序退出后清理临时数据。

# 18. 日志

基础日志级别：

```text
INFO
WARNING
ERROR
```

记录：

- 启动时间
- 检测请求时间
- 请求耗时
- 调用成功/失败
- JSON 解析情况
- 错误类型

禁止记录：

- API Key
- 用户原始图片
- 完整 Prompt
- 模型详细内部推理过程

# 19. 配置与 API Key

使用：

```text
.env
```

提供：

```text
.env.example
```

示例：

```text
ARK_API_KEY=
ARK_BASE_URL=
ARK_MODEL=
APP_MODE=online
HOST=0.0.0.0
PORT=8501
```

API Key 不得硬编码、不得写入 Git、不得写日志、不得通过命令行参数明文传递。

安装器首次运行时交互式询问必要参数，并隐藏 API Key 输入。

# 20. Demo / 离线备用模式

内部支持：

```text
APP_MODE=online
APP_MODE=demo
```

`online`：真实调用 Doubao-Seed-2.0-lite。

`demo`：使用预先准备的演示结果或本地缓存。

Demo 模式必须用于演示容灾，不得伪装为实时模型结果。

用户页面不显示运行模式。

# 21. 一键安装与生命周期管理

必须支持：

- GitHub 一键安装
- 安装
- 启动
- 停止
- 重启
- 更新
- 卸载
- 修改配置
- 状态检查
- 日志查看

推荐命令：

```bash
huangjing start
huangjing stop
huangjing restart
huangjing update
huangjing uninstall
huangjing config
huangjing status
huangjing logs
huangjing check
```

同时支持交互式菜单。

# 22. Linux 一键安装

提供：

```text
scripts/install.sh
scripts/run.sh
scripts/check.sh
```

支持类似：

```bash
curl -fsSL https://raw.githubusercontent.com/<ORG>/<REPO>/main/install.sh | bash
```

安装器自动完成：

```text
检查系统
↓
检查 Python
↓
检查 Git
↓
创建虚拟环境
↓
安装依赖
↓
询问 API 配置
↓
询问 Web 配置
↓
询问 HTTPS 配置
↓
写入配置
↓
配置服务
↓
健康检查
```

至少优先保证 Debian/Ubuntu 系列 Linux。

# 23. Windows 一键安装

提供：

```text
scripts/install.bat
scripts/run.bat
scripts/check.bat
```

至少支持双击安装脚本完成：

- Python 检查
- 虚拟环境创建
- 依赖安装
- API 参数配置
- Web 参数配置

# 24. HTTPS

HTTPS 是正式部署能力。

Linux 公网部署优先采用：

> **Caddy + Let's Encrypt**

安装时询问：

```text
是否使用 HTTPS？
域名：
证书邮箱：
```

自动完成：

```text
检查 DNS
↓
检查 80/443 端口
↓
安装/检查 Caddy
↓
配置反向代理
↓
申请 Let's Encrypt SSL/TLS 证书
↓
启用 HTTPS
↓
配置自动续期
↓
HTTPS 健康检查
```

推荐结构：

```text
Internet
   ↓
Caddy :443
   ↓
Streamlit :8501
```

# 25. HTTPS 更新与卸载

`huangjing update` 不得破坏：

- `.env`
- Caddy 配置
- 域名配置
- SSL 证书
- 用户配置

更新流程：

```text
备份配置
↓
获取新版本
↓
更新代码
↓
更新依赖
↓
保留部署配置
↓
重启
↓
HTTP/HTTPS 健康检查
```

卸载时询问是否删除程序、虚拟环境、配置、日志、Caddy 配置、SSL 证书及临时数据；默认避免无确认的危险删除。

# 26. 配置修改

命令：

```bash
huangjing config
```

可修改：

```text
API Key
API Endpoint
Model
监听地址
端口
HTTPS
域名
证书邮箱
日志级别
```

修改 API Key 时隐藏输入，并在修改后执行必要配置检查。

# 27. 环境检查

命令：

```bash
huangjing check
```

至少检查：

```text
✓ Python
✓ pip
✓ 虚拟环境
✓ 项目依赖
✓ .env
✓ API Key 是否存在
✓ 模型配置
✓ 网络
✓ API 可访问性
✓ Caddy
✓ HTTPS
✓ 服务端口
```

不输出 API Key 内容。

# 28. 推荐项目体验

## Linux

```bash
curl -fsSL https://raw.githubusercontent.com/<ORG>/<REPO>/main/install.sh | bash
```

然后按提示输入：

```text
API Key
Endpoint
Model
端口
是否 HTTPS
域名
邮箱
```

完成后：

```bash
huangjing status
```

## Windows

双击：

```text
install.bat
```

之后：

```text
run.bat
```

# 29. 开发优先级

## P0：必须完成

- Streamlit UI
- 图片上传
- Prompt
- Doubao-Seed-2.0-lite 调用
- JSON 解析
- 三项指标
- 程序最终判定
- 错误处理
- `.env`
- Windows 安装
- Linux 安装
- GitHub 获取代码
- 基础 HTTPS
- Caddy
- Let's Encrypt

## P1：建议完成

- Few-shot
- 会话历史记录
- 日志
- `huangjing` CLI
- update / uninstall / config / check
- Demo 备用模式
- HTTPS 自动健康检查

## P2：校赛后再做

- ResNet18
- 真实黄精数据集
- 专家标注
- 真正模型置信度
- 多视角融合
- 异常区域坐标/Mask
- 专门的霉变识别模型
- 数据库
- 人工复核系统
- 数据回流训练

# 30. 明确禁止的过度实现

当前版本不要自行增加：

- 用户登录系统
- 权限系统
- 数据库集群
- Redis
- 消息队列
- 微服务
- Kubernetes
- 手机 App
- 微信小程序
- 云原生复杂部署
- 复杂目标检测模型
- 复杂图像分割模型
- 自行训练 ResNet18
- 虚构实验指标

# 31. 验收标准

第一版完成后至少应满足：

```text
上传符合要求的黄精图片
    ↓
成功调用视觉模型
    ↓
返回合法 JSON
    ↓
程序正确解析
    ↓
三个指标独立展示
    ↓
程序按照规则计算最终结果
    ↓
页面显示结果
```

并通过：

1. 正常九蒸九晒黄精 → `sample_valid=true`
2. 生鲜黄精 → 能识别为不符合评价对象
3. 多根严重堆叠 → 无法独立评价时 `sample_valid=false`
4. 多根但存在明显独立目标 → 允许 `sample_valid=true`
5. 相同图片重复请求 → 结果尽可能稳定
6. 非法 JSON → 程序不崩溃
7. API 超时 → 有限自动重试并提示用户
8. API Key 错误 → 提示配置问题，不进行无意义重试
9. HTTPS → 公网域名正常访问
10. 更新 → 配置、HTTPS 和服务能够恢复运行

# 32. 关键开发原则

> **视觉模型负责看图，程序负责规则，系统负责呈现。**

不要为了让 Demo 看起来像 AI 而堆假的神经网络动画。

不要把当前使用的大模型冒充成已经训练完成的 ResNet18。

不要把 Mock/演示数据冒充成真实实验结果。

不要让模型直接决定最终业务结论。

不要让一个指标的结果自动修改另一个指标。

不要为了五天 MVP 引入不必要的基础设施。

# 33. 后续 ResNet18 替换目标

当前：

```text
图片
 ↓
Doubao-Seed-2.0-lite
 ↓
三个指标
 ↓
规则判定
```

未来：

```text
图片
 ↓
黄精主体预处理
 ↓
ResNet18 / 多任务模型
 ↓
三个指标
 ↓
规则判定
```

真实模型阶段再建立：

- 专用黄精图像数据集
- 专家标签
- Train / Validation / Test
- Precision
- Recall
- F1
- Confusion Matrix
- 真正模型置信度

这些不是当前 MVP 的内容。
