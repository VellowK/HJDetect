# -*- coding: utf-8 -*-
"""统一日志配置。

- 日志写入 logs/ 目录, 同时输出到控制台
- 禁止记录: API Key、用户原始图片、完整 Prompt、模型内部推理过程
- 各模块通过 get_logger(__name__) 获取 logger

注意: 调用方负责不向日志传入敏感内容; 本文件同时提供一个
sanitize() 辅助函数, 用于在记录动态字符串前剔除疑似 Key 的片段。
"""

import logging
import os
import re

# 项目根目录 = core/ 的上一级 (本地计算, 避免与 config.py 循环依赖)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 疑似密钥片段 (sk- 开头 / 长十六进制串 / Bearer), 记录前替换
_SENSITIVE_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9\-_]{8,}|Bearer\s+\S+|[A-Fa-f0-9]{32,})"
)

_configured = False


def sanitize(text):
    """剔除字符串中的疑似密钥片段, 返回可安全记录的文本。"""
    if not isinstance(text, str):
        text = str(text)
    return _SENSITIVE_PATTERN.sub("[REDACTED]", text)


def _ensure_dir():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        # 日志目录不可创建时降级为仅控制台输出, 不阻塞主流程
        return False
    return True


def setup_logging(level=None):
    """初始化根项目日志, 幂等调用。"""
    global _configured
    if _configured:
        return

    level_name = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    level_value = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger("core")
    root.setLevel(level_value)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if _ensure_dir():
        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            root.warning("日志文件无法创建, 仅输出到控制台")

    _configured = True


def get_logger(name):
    """获取模块 logger, 首次调用时自动完成日志初始化。"""
    setup_logging()
    if not name.startswith("core"):
        name = "core." + name
    return logging.getLogger(name)
