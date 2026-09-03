# -*- coding: utf-8 -*-
"""模型输出 JSON 解析与校验。

职责:
- 从模型响应文本中解析 JSON (支持一次轻量提取/修复)
- 校验 sample_valid 与三个指标的枚举值合法性
- 返回结构化 AnalysisResult, 供 evaluator 使用

判定原则: 本模块只做结构校验, 不做业务判定; overall 字段
原样保留仅供展示比对, 程序端不信任它。
"""

import json
import re
from dataclasses import dataclass

from core.logger import get_logger

logger = get_logger(__name__)

# 枚举定义 (与规格书 4/9/10 节一致)
COMPLETENESS_LEVELS = ("高", "中", "低")
COLOR_UNIFORMITY_LEVELS = ("高", "中", "低")
MOLD_RISK_LEVELS = ("低风险", "中风险", "高风险")
OVERALL_LEVELS = ("合格", "建议人工复核", "不合格", "无法评价")

VALID_ENUMS = {
    "completeness": COMPLETENESS_LEVELS,
    "color_uniformity": COLOR_UNIFORMITY_LEVELS,
    "mold_risk": MOLD_RISK_LEVELS,
}


class ParseError(Exception):
    """模型输出无法解析为合法结构。"""


@dataclass
class AnalysisResult:
    """解析后的结构化模型输出。"""

    sample_valid: bool
    completeness: str = None
    color_uniformity: str = None
    mold_risk: str = None
    overall: str = None  # 模型自报, 仅作展示比对, 不作为业务依据
    reason: str = ""
    anomaly_description: str = ""

    def to_dict(self):
        return {
            "sample_valid": self.sample_valid,
            "completeness": self.completeness,
            "color_uniformity": self.color_uniformity,
            "mold_risk": self.mold_risk,
            "overall": self.overall,
            "reason": self.reason,
            "anomaly_description": self.anomaly_description,
        }


def _extract_json_text(text):
    """从模型响应中提取候选 JSON 文本。

    依次尝试: 剥离 Markdown 代码块 -> 直接整体解析 -> 提取首个 {...} 块。
    """
    if not text or not isinstance(text, str):
        raise ParseError("模型响应为空或非文本")

    stripped = text.strip()

    # Markdown ```json ... ``` 代码块
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    # 提取第一个配平的 { ... } 块 (处理前后缀说明文字)
    start = stripped.find("{")
    if start == -1:
        raise ParseError("模型响应中未找到 JSON 对象")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : i + 1]

    raise ParseError("JSON 对象未正确闭合")


def _light_repair(candidate):
    """轻量 JSON 修复: 中文引号替换、单引号转双引号、去除尾逗号。"""
    repaired = candidate
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)  # 尾逗号
    if "'" in repaired:
        # 仅在双引号未大量出现时尝试单引号转双引号, 避免破坏合法 JSON 内容
        if '"' not in repaired:
            repaired = repaired.replace("'", '"')
        else:
            # 混合引号: 把成对单引号包住的 key/value 转为双引号
            repaired = re.sub(r"'([^']*)'", lambda m: '"' + m.group(1).replace('"', '\\"') + '"', repaired)
    return repaired


def _parse_json_object(text):
    candidates = []
    try:
        extracted = _extract_json_text(text)
        candidates.append(extracted)
    except ParseError as exc:
        raise ParseError(str(exc))

    candidates.append(_light_repair(candidates[0]))

    last_error = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed

    logger.warning("JSON 解析失败: %s", last_error)
    raise ParseError("模型输出不是合法 JSON")


def _coerce_bool(value, field):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes"):
            return True
        if normalized in ("false", "0", "no"):
            return False
    if value is None:
        return None
    raise ParseError("字段 %s 的值 %r 不是合法布尔值" % (field, value))


def _validate_enum(value, field, allowed, required=True):
    if value is None:
        if required:
            raise ParseError("缺少必填字段: %s" % field)
        return None
    if value not in allowed:
        raise ParseError(
            "字段 %s 的值 %r 不在允许范围 %s 内" % (field, value, list(allowed))
        )
    return value


def parse_model_output(text):
    """模块级入口 (app.py 编排契约): 解析文本并返回 dict。

    与 parse_model_response 等价, 但返回纯数据 dict, 便于
    evaluator 与 UI 直接按字段读取。
    """
    return parse_model_response(text).to_dict()


def parse_model_response(text):
    """解析模型响应文本, 返回 AnalysisResult; 失败抛出 ParseError。

    规则 (与规格书 9/10 节一致):
    - sample_valid 必填
    - sample_valid=true 时三个指标必填且枚举合法
    - sample_valid=false 时三个指标应为 null, overall 应为 无法评价
    """
    data = _parse_json_object(text)

    if "sample_valid" not in data:
        raise ParseError("缺少必填字段: sample_valid")
    sample_valid = _coerce_bool(data["sample_valid"], "sample_valid")
    if sample_valid is None:
        raise ParseError("字段 sample_valid 不能为空")

    if sample_valid:
        result = AnalysisResult(sample_valid=True)
        result.completeness = _validate_enum(
            data.get("completeness"), "completeness", COMPLETENESS_LEVELS
        )
        result.color_uniformity = _validate_enum(
            data.get("color_uniformity"), "color_uniformity", COLOR_UNIFORMITY_LEVELS
        )
        result.mold_risk = _validate_enum(
            data.get("mold_risk"), "mold_risk", MOLD_RISK_LEVELS
        )
        overall = data.get("overall")
        if overall is not None and overall not in OVERALL_LEVELS:
            # 模型自报 overall 非法不影响主流程, 忽略即可
            logger.warning("模型自报 overall=%r 非法, 已忽略", overall)
            overall = None
        result.overall = overall
        result.reason = data.get("reason") or ""
        result.anomaly_description = data.get("anomaly_description") or ""
        if not isinstance(result.reason, str):
            result.reason = str(result.reason)
        if not isinstance(result.anomaly_description, str):
            result.anomaly_description = str(result.anomaly_description)
        return result

    # 无效样本
    result = AnalysisResult(sample_valid=False)
    for field in ("completeness", "color_uniformity", "mold_risk"):
        value = data.get(field)
        if value is not None:
            logger.warning("sample_valid=false 时 %s 应为 null, 收到 %r, 已置空", field, value)
        setattr(result, field, None)
    result.overall = "无法评价"
    result.reason = data.get("reason") or ""
    result.anomaly_description = ""
    if not isinstance(result.reason, str):
        result.reason = str(result.reason)
    return result
