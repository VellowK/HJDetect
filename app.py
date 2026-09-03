# -*- coding: utf-8 -*-
"""智鉴黄精 - AI品质检测系统 前端页面。

职责边界（与技术规格 v1.0 对应）：
- 视觉分析由 core/analyzer 完成，结果解析由 core/parser 完成，
  最终业务判定由 core/evaluator 完成，输入校验由 core/validator 完成。
- 本文件只负责：页面结构、输入收集、流程编排、结果呈现、会话历史与错误提示。
- 前台不展示任何运行模式与技术细节；检测指令文本仅经内存传递，不在界面出现。
"""

import base64
import importlib
import io
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import streamlit as st
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass

APP_MODE = os.getenv("APP_MODE", "online").strip().lower()
MAX_FILE_MB = 10
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
HISTORY_LIMIT = 20
ALLOWED_TYPES = ("jpg", "jpeg", "png")

OVERALL_PASS = "合格"
OVERALL_REVIEW = "建议人工复核"
OVERALL_REJECT = "不合格"
OVERALL_INVALID = "无法评价"

# ---------------------------------------------------------------------------
# 日志：只记录运行状态，不记录密钥、原始图片、提示词与内部推理过程
# ---------------------------------------------------------------------------


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("zhijian_huangjing")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    try:
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "app.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        pass
    return logger


logger = _setup_logger()

# ---------------------------------------------------------------------------
# 核心组件装载（容错：组件缺失时页面仍可打开，检测时给出友好提示）
# ---------------------------------------------------------------------------


def _import_core(name: str):
    try:
        return importlib.import_module(f"core.{name}")
    except Exception as exc:  # ImportError 或组件自身装载失败
        logger.warning("核心组件 core.%s 装载失败: %r", name, exc)
        return None


def _resolve(module, names):
    if module is None:
        return None
    for name in names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None


core_validator = _import_core("validator")
core_analyzer = _import_core("analyzer")
core_parser = _import_core("parser")
core_evaluator = _import_core("evaluator")

_validate_fn = _resolve(
    core_validator, ("validate_image", "validate_image_input", "validate", "validate_upload")
)
_analyze_fn = _resolve(core_analyzer, ("analyze_image", "analyze", "run_analysis"))
_parse_fn = _resolve(core_parser, ("parse_response", "parse", "parse_model_output", "extract_json"))
_evaluate_fn = _resolve(core_evaluator, ("evaluate", "evaluate_result", "final_evaluate", "judge"))


def _load_system_prompt() -> str:
    """从 prompts/system.txt 载入分析指令文本（文件名按规格固定）。"""
    path = BASE_DIR / "prompts" / "system.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.error("读取系统提示词文件失败: %r", exc)
        return ""
    return text


class DetectionError(Exception):
    """携带用户友好信息的检测流程异常。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message


# ---------------------------------------------------------------------------
# 检测流程编排
# ---------------------------------------------------------------------------


def _call_validator(image_bytes: bytes, filename: str):
    if _validate_fn is None:
        return True, ""
    try:
        return _validate_fn(image_bytes, filename)
    except TypeError:
        return _validate_fn(image_bytes)


def _call_analyzer(image_bytes: bytes, system_prompt: str) -> str:
    if _analyze_fn is not None:
        try:
            return _analyze_fn(image_bytes, system_prompt)
        except TypeError:
            return _analyze_fn(image_bytes)
    # 分析组件未就绪时，仅在演示备用模式下使用内置演示结果，保证流程可走通
    if APP_MODE == "demo":
        logger.warning("分析组件未就绪，演示备用模式下使用内置演示结果")
        return build_fallback_demo_payload()
    logger.error("分析组件未就绪且当前非演示备用模式")
    raise DetectionError("检测服务暂时不可用，请稍后再试。")


def _call_parser(raw_text: str) -> dict:
    if _parse_fn is None:
        raise DetectionError("本次检测结果无法正常解读，请重新尝试。")
    try:
        return _parse_fn(raw_text)
    except Exception as exc:
        logger.warning("结果解读失败: %r", exc)
        raise DetectionError("本次检测结果无法正常解读，请重新尝试。") from exc


def _call_evaluator(parsed: dict) -> dict:
    if _evaluate_fn is None:
        raise DetectionError("结果判定组件未就绪，请联系管理员。")
    try:
        return _evaluate_fn(parsed)
    except Exception as exc:
        logger.warning("最终判定失败: %r", exc)
        raise DetectionError("本次结果判定出现问题，请重新尝试。") from exc


def build_fallback_demo_payload() -> str:
    """演示备用模式下的内置结果（仅在该模式且分析组件缺失时使用）。"""
    import json

    payload = {
        "sample_valid": True,
        "completeness": "高",
        "color_uniformity": "中",
        "mold_risk": "低风险",
        "overall": OVERALL_PASS,
        "reason": "主体结构基本完整，色泽存在一定局部差异，未发现明显疑似霉变异常。",
        "anomaly_description": "",
    }
    return json.dumps(payload, ensure_ascii=False)


def run_detection(image_bytes: bytes, filename: str) -> dict:
    """完整检测流程：校验 -> 分析 -> 解读 -> 判定。"""
    started = datetime.now()
    logger.info("收到检测请求")

    try:
        ok, message = _call_validator(image_bytes, filename)
    except Exception as exc:
        logger.warning("输入校验组件异常: %r", exc)
        ok, message = True, ""  # 校验组件异常时放行，由后续流程兜底
    if not ok:
        logger.info("输入校验未通过")
        raise DetectionError(message or "图片不符合检测要求，请更换图片后重试。")

    system_prompt = _load_system_prompt()
    if not system_prompt:
        raise DetectionError("系统配置不完整，无法进行检测，请联系管理员。")

    try:
        raw_text = _call_analyzer(image_bytes, system_prompt)
    except DetectionError:
        raise
    except Exception as exc:
        logger.error("分析请求失败: %r", exc)
        raise DetectionError("检测服务暂时不可用，请稍后再试。") from exc

    parsed = _call_parser(raw_text)
    final_result = _call_evaluator(parsed)

    elapsed = (datetime.now() - started).total_seconds()
    logger.info("检测完成，耗时 %.2f 秒", elapsed)
    return final_result


# ---------------------------------------------------------------------------
# 会话状态与历史记录
# ---------------------------------------------------------------------------

OVERALL_BADGE = {
    OVERALL_PASS: ("✅", "success"),
    OVERALL_REVIEW: ("⚠️", "warning"),
    OVERALL_REJECT: ("🚫", "error"),
    OVERALL_INVALID: ("ℹ️", "info"),
}


def make_thumbnail(image_bytes: bytes) -> str:
    """生成会话内临时缩略图（base64），不写入磁盘。"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((160, 160))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def append_history(result: dict, thumb_b64: str) -> None:
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "thumb": thumb_b64,
        "completeness": result.get("completeness"),
        "color_uniformity": result.get("color_uniformity"),
        "mold_risk": result.get("mold_risk"),
        "overall": result.get("overall", OVERALL_INVALID),
    }
    st.session_state.setdefault("history", [])
    st.session_state["history"].insert(0, entry)
    del st.session_state["history"][HISTORY_LIMIT:]


def render_history() -> None:
    history = st.session_state.get("history", [])
    st.subheader("最近检测记录")
    if not history:
        st.caption("暂无检测记录")
        return

    header = st.columns([1.2, 3.2, 1.4, 1.4, 1.4, 1.6])
    for col, text in zip(
        header, ("检测时间", "图片", "根茎完整度", "色泽均匀度", "霉变风险", "综合评价")
    ):
        col.markdown(f"**{text}**")

    for item in history:
        row = st.columns([1.2, 3.2, 1.4, 1.4, 1.4, 1.6])
        row[0].write(item["time"])
        if item.get("thumb"):
            row[1].image(base64.b64decode(item["thumb"]), width=96)
        else:
            row[1].write("—")
        row[2].write(item.get("completeness") or "—")
        row[3].write(item.get("color_uniformity") or "—")
        row[4].write(item.get("mold_risk") or "—")
        overall = item.get("overall") or OVERALL_INVALID
        badge, kind = OVERALL_BADGE.get(overall, ("ℹ️", "info"))
        row[5].write(f"{badge} {overall}")

    if st.button("清空检测记录"):
        st.session_state["history"] = []
        st.rerun()


# ---------------------------------------------------------------------------
# 结果展示
# ---------------------------------------------------------------------------


def render_result(result: dict, thumb_b64: str) -> None:
    st.subheader("检测结果")

    sample_valid = result.get("sample_valid", True)
    completeness = result.get("completeness")
    color_uniformity = result.get("color_uniformity")
    mold_risk = result.get("mold_risk")
    overall = result.get("overall") or OVERALL_INVALID

    if not sample_valid:
        st.info("图片中未找到可独立评价的黄精主体，本次无法给出品质结论。可调整拍摄角度或更换图片后重试。")

    c1, c2, c3 = st.columns(3)
    c1.metric("根茎完整度", completeness or OVERALL_INVALID)
    c2.metric("色泽均匀度", color_uniformity or OVERALL_INVALID)
    c3.metric("霉变风险", mold_risk or OVERALL_INVALID)

    badge, kind = OVERALL_BADGE.get(overall, ("ℹ️", "info"))
    box = {"success": st.success, "warning": st.warning, "error": st.error, "info": st.info}[kind]
    box(f"综合评价：{overall} {badge}")

    reason = (result.get("reason") or "").strip()
    anomaly = (result.get("anomaly_description") or "").strip()
    with st.container(border=True):
        st.markdown("**检测依据**")
        st.write(reason or "未提供视觉依据。")
        if anomaly:
            st.caption(f"异常区域：{anomaly}")

    append_history(result, thumb_b64)


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------

st.set_page_config(page_title="智鉴黄精 - AI品质检测系统", page_icon="🌿", layout="centered")

st.title("智鉴黄精 - AI品质检测系统")
st.caption("九蒸九晒黄精成品外观品质辅助评价")

uploaded = st.file_uploader(
    "上传黄精图片",
    type=list(ALLOWED_TYPES),
    help=f"支持 {'/'.join(ALLOWED_TYPES).upper()} 格式，单张不超过 {MAX_FILE_MB} MB；"
    "建议浅色干净背景、主体清晰，图片短边不低于 720 像素。",
)

if uploaded is not None:
    image_bytes = uploaded.getvalue()
    if len(image_bytes) > MAX_FILE_BYTES:
        st.error(f"图片超过 {MAX_FILE_MB} MB，请压缩后重新上传。")
        uploaded = None
    else:
        try:
            st.image(image_bytes, caption="图片预览", use_container_width=True)
        except Exception:
            st.error("图片无法正常读取，请更换图片后重试。")
            uploaded = None

if uploaded is not None and st.button("开始检测", type="primary", use_container_width=True):
    with st.spinner("正在分析图片，请稍候……"):
        try:
            result = run_detection(image_bytes, uploaded.name)
            st.session_state["last_result"] = result
            st.session_state["last_thumb"] = make_thumbnail(image_bytes)
        except DetectionError as exc:
            st.error(exc.user_message)
        except Exception:
            logger.exception("检测流程出现未预期错误")
            st.error("检测过程中出现问题，请重新尝试；若多次失败请联系管理员。")

# 检测结果在同一位置持续展示，且只渲染一次，避免重复写入历史记录
if "last_result" in st.session_state:
    render_result(st.session_state["last_result"], st.session_state.get("last_thumb", ""))

st.divider()
render_history()
