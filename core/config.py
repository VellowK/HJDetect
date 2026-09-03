# -*- coding: utf-8 -*-
"""环境变量配置读取, 供 core 各模块共享。

使用 python-dotenv 加载项目根目录下的 .env 文件, 环境变量优先于 .env 内容。

环境变量:
- ARK_API_KEY  : ARK 开放平台 API Key (online 模式必需)
- ARK_BASE_URL : ARK API 基础地址 (默认官方地址)
- ARK_MODEL    : 视觉模型名称 (默认 Doubao-Seed-2.0-lite)
- APP_MODE     : 运行模式, online / demo (默认 online)
- LOG_LEVEL    : 日志级别 (默认 INFO)
"""

import os

# 项目根目录 = core/ 的上一级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)
except ImportError:
    # python-dotenv 缺失时的内置兜底: 解析 KEY=VALUE / # 注释 / export 前缀
    def _load_env_file(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                lines = fh.readlines()
        except OSError:
            return
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value

    _load_env_file(os.path.join(PROJECT_ROOT, ".env"))
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-2.0-lite"

VALID_MODES = ("online", "demo")


class ConfigError(Exception):
    """配置缺失或非法。"""


def get_env(name, default=None):
    return os.environ.get(name, default)


def get_mode():
    """返回运行模式, 非法值回退到 online 并记录警告。"""
    raw = (os.environ.get("APP_MODE") or "online").strip().lower()
    if raw not in VALID_MODES:
        from core.logger import get_logger

        get_logger(__name__).warning(
            "APP_MODE=%r 非法, 回退到 online", raw
        )
        return "online"
    return raw


def require_online_config():
    """online 模式必需的配置缺失时抛出 ConfigError。"""
    api_key = (os.environ.get("ARK_API_KEY") or "").strip()
    if not api_key:
        raise ConfigError("缺少 ARK_API_KEY 环境变量, 无法调用在线视觉模型。")
    return {
        "api_key": api_key,
        "base_url": (os.environ.get("ARK_BASE_URL") or "").strip() or DEFAULT_BASE_URL,
        "model": (os.environ.get("ARK_MODEL") or "").strip() or DEFAULT_MODEL,
    }
