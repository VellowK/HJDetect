# -*- coding: utf-8 -*-
"""Prompt 装配辅助。

规格书第 8 节要求 Prompt 独立存储于 prompts/ 目录 (system.txt),
本模块负责读取并在缺失时提供内置兜底文案。完整 Prompt 不写入日志。
"""

import os

from core.config import PROJECT_ROOT
from core.logger import get_logger

logger = get_logger(__name__)

PROMPTS_DIR = os.path.join(PROJECT_ROOT, "prompts")
SYSTEM_PROMPT_FILE = os.path.join(PROMPTS_DIR, "system.txt")

# 内置兜底 Prompt (prompts/system.txt 缺失时使用, 与规格书输出 Schema 对齐)
FALLBACK_SYSTEM_PROMPT = """你是黄精成品外观品质评价助手。请分析用户上传的黄精图片, 严格只返回一个 JSON 对象, 不要输出任何其他文字。

评价对象是九蒸九晒工艺完成后的黄精成品中的单根主体。三个指标完全独立判断, 互不影响。

1. sample_valid (布尔): 图片是否存在可独立可靠评价的单根黄精主体。主体不存在、严重堆叠、严重遮挡、严重模糊/过暗/过曝时为 false。
2. completeness (高/中/低): 根茎完整度。只判断结构连续性: 明显断裂/缺失为低; 局部破损但主体基本保持为中; 结构基本完整为高。天然弯曲、节状膨大、粗细不均不算低。
3. color_uniformity (高/中/低): 色泽均匀度。只判断同一根内部色泽分布: 明显异常色块/斑驳为低; 一定局部色差但整体协调为中; 整体均匀为中高。绝对颜色深浅不决定等级。
4. mold_risk (低风险/中风险/高风险): 霉变风险。只判断疑似霉变外观特征: 无异常为低风险; 局部异常但无法可靠区分色差为中风险; 颜色+纹理+形态异常组合明显为高风险。颜色较深本身不代表高风险。

JSON 格式:
{"sample_valid": true, "completeness": "高", "color_uniformity": "中", "mold_risk": "低风险", "overall": "合格", "reason": "...", "anomaly_description": ""}

sample_valid=false 时三个指标为 null, overall 为 "无法评价"。
reason 为一两句简短视觉依据; anomaly_description 描述异常大致位置与表现, 无异常则为空字符串。"""


def load_system_prompt():
    """读取 prompts/system.txt, 缺失或读取失败时返回内置兜底文案。"""
    try:
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        if text:
            return text
        logger.warning("prompts/system.txt 为空, 使用内置兜底 Prompt")
    except FileNotFoundError:
        logger.warning("prompts/system.txt 不存在, 使用内置兜底 Prompt")
    except OSError as exc:
        logger.warning("prompts/system.txt 读取失败 (%s), 使用内置兜底 Prompt", exc)
    return FALLBACK_SYSTEM_PROMPT


def build_user_prompt():
    """返回 {"system": ...} 结构, 供 analyzer 组装 messages。

    用户侧文本由 analyzer 固定拼接, 这里只提供 system 部分。
    """
    return {"system": load_system_prompt()}
