# -*- coding: utf-8 -*-
"""最终综合判定规则。

核心原则: 程序不信任模型自报的 overall 字段, 只依据三个独立指标
按固定优先级重新执行判定 (规格书第 6 节):

    1. sample_valid=false  -> INVALID / 无法评价
    2. mold_risk=高风险     -> REJECT  / 不合格
    3. mold_risk=中风险     -> REVIEW  / 建议人工复核
    4. completeness=低      -> REJECT  / 不合格
    5. color_uniformity=低  -> REJECT  / 不合格
    6. 其他                 -> PASS    / 合格
"""

from core.logger import get_logger
from core.parser import AnalysisResult

logger = get_logger(__name__)

# 判定结果常量
PASS = "PASS"
REVIEW = "REVIEW"
REJECT = "REJECT"
INVALID = "INVALID"

# 判定结果 -> 中文展示文案
VERDICT_LABELS = {
    PASS: "合格",
    REVIEW: "建议人工复核",
    REJECT: "不合格",
    INVALID: "无法评价",
}


class Verdict:
    """最终判定结果。"""

    def __init__(self, code, label, matched_rule):
        self.code = code          # PASS / REVIEW / REJECT / INVALID
        self.label = label        # 中文文案
        self.matched_rule = matched_rule  # 命中的规则说明, 供日志/调试

    def to_dict(self):
        return {
            "code": self.code,
            "label": self.label,
            "matched_rule": self.matched_rule,
        }

    def __repr__(self):
        return "Verdict(code=%r, label=%r)" % (self.code, self.label)


def evaluate_quality(analysis_result):
    """根据 AnalysisResult 的三个独立指标执行最终判定。

    参数 analysis_result: core.parser.AnalysisResult
    返回 core.evaluator.Verdict
    抛出 TypeError: 传入对象不是 AnalysisResult
    """
    if not isinstance(analysis_result, AnalysisResult):
        raise TypeError("evaluate_quality 需要 AnalysisResult, 收到 %r" % type(analysis_result).__name__)

    # 规则 1: 输入无效 -> 无法评价 (不代表品质不合格)
    if not analysis_result.sample_valid:
        return Verdict(INVALID, VERDICT_LABELS[INVALID], "sample_valid=false")

    # 规则 2/3: 霉变风险优先于完整度与色泽
    if analysis_result.mold_risk == "高风险":
        return Verdict(REJECT, VERDICT_LABELS[REJECT], "mold_risk=高风险")
    if analysis_result.mold_risk == "中风险":
        return Verdict(REVIEW, VERDICT_LABELS[REVIEW], "mold_risk=中风险")

    # 规则 4/5: 完整度、色泽任一为低 -> 不合格
    if analysis_result.completeness == "低":
        return Verdict(REJECT, VERDICT_LABELS[REJECT], "completeness=低")
    if analysis_result.color_uniformity == "低":
        return Verdict(REJECT, VERDICT_LABELS[REJECT], "color_uniformity=低")

    # 规则 6: 其余情况合格
    return Verdict(PASS, VERDICT_LABELS[PASS], "default PASS")


def evaluate(parsed):
    """模块级入口 (app.py 编排契约): 依据 dict 执行最终判定, 返回 dict。

    不信任传入 dict 中的 overall 字段, 只依据 sample_valid 与
    三个独立指标重新判定。字段缺失或非法时按保守规则处理。
    """
    sample_valid = parsed.get("sample_valid") if isinstance(parsed, dict) else None

    # sample_valid 缺失或非法时保守视为无效样本 (无法评价, 而非误判合格)
    if not isinstance(sample_valid, bool):
        logger.warning("sample_valid 缺失或非法 (%r), 按无效样本处理", sample_valid)
        return {
            "sample_valid": False,
            "completeness": None,
            "color_uniformity": None,
            "mold_risk": None,
            "overall": VERDICT_LABELS[INVALID],
            "reason": (parsed.get("reason") if isinstance(parsed, dict) else "") or "",
            "anomaly_description": "",
            "verdict": INVALID,
        }

    if not sample_valid:
        overall = VERDICT_LABELS[INVALID]
    elif parsed.get("mold_risk") == "高风险":
        overall = VERDICT_LABELS[REJECT]
    elif parsed.get("mold_risk") == "中风险":
        overall = VERDICT_LABELS[REVIEW]
    elif parsed.get("completeness") == "低":
        overall = VERDICT_LABELS[REJECT]
    elif parsed.get("color_uniformity") == "低":
        overall = VERDICT_LABELS[REJECT]
    else:
        overall = VERDICT_LABELS[PASS]

    result = dict(parsed)
    result["overall"] = overall
    return result
