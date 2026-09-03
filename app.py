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
import json
import logging
import os
import sys
import time
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
HEALTH_TTL_SECONDS = 20 * 60  # 状态灯每 20 分钟真实探测一次

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
_health_fn = _resolve(core_analyzer, ("health_check", "healthcheck", "ping"))


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
# 服务健康探测（状态指示灯）：每 20 分钟真实向 API 发一次轻量测试请求
# ---------------------------------------------------------------------------


def probe_service_health(force: bool = False) -> dict:
    """带 TTL 缓存的健康探测。

    返回 {"ok": bool, "detail": str, "checked_at": "HH:MM:SS"}。
    结果缓存在 session_state，20 分钟内复用，避免每次交互都打 API。
    """
    cache = st.session_state.get("_health_cache")
    now = time.monotonic()
    if (
        not force
        and cache is not None
        and (now - cache.get("_ts", 0)) < HEALTH_TTL_SECONDS
    ):
        return cache

    ok, detail = False, "健康检查不可用"
    if _health_fn is not None:
        try:
            res = _health_fn()
            if isinstance(res, tuple) and len(res) >= 2:
                ok, detail = bool(res[0]), str(res[1])
            elif isinstance(res, dict):
                ok, detail = bool(res.get("ok")), str(res.get("detail", ""))
            else:
                ok, detail = bool(res), "在线" if res else "离线"
        except Exception as exc:
            logger.warning("健康探测异常: %r", exc)
            ok, detail = False, "探测异常"
    else:
        # 核心组件缺失时，无法确认后端连通
        ok, detail = False, "服务未就绪"

    result = {
        "ok": ok,
        "detail": detail,
        "checked_at": datetime.now().strftime("%H:%M:%S"),
        "_ts": now,
    }
    st.session_state["_health_cache"] = result
    return result


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


def _to_result_dict(result) -> dict:
    """把 evaluator 返回值统一成 dict（兼容 dataclass / 对象）。"""
    if isinstance(result, dict):
        return result
    for attr in ("to_dict", "_asdict"):
        fn = getattr(result, attr, None)
        if callable(fn):
            return fn()
    if hasattr(result, "__dict__"):
        return dict(result.__dict__)
    return {"overall": OVERALL_INVALID}


def run_detection(image_bytes: bytes, filename: str, log) -> dict:
    """完整检测流程：校验 -> 分析 -> 解读 -> 判定。

    log 为回调 (str) -> None，用于把每一步进度写入右侧实时日志面板。
    """
    started = datetime.now()
    logger.info("收到检测请求")
    log("收到检测请求，开始处理…")

    log("步骤 1/4 · 输入校验")
    try:
        ok, message = _call_validator(image_bytes, filename)
    except Exception as exc:
        logger.warning("输入校验组件异常: %r", exc)
        ok, message = True, ""
    if not ok:
        logger.info("输入校验未通过")
        log("✗ 输入校验未通过")
        raise DetectionError(message or "图片不符合检测要求，请更换图片后重试。")
    log("✓ 校验通过")

    system_prompt = _load_system_prompt()
    if not system_prompt:
        log("✗ 系统配置不完整")
        raise DetectionError("系统配置不完整，无法进行检测，请联系管理员。")

    log("步骤 2/4 · 调用视觉模型分析（可能需要数秒）")
    try:
        raw_text = _call_analyzer(image_bytes, system_prompt)
    except DetectionError:
        log("✗ 模型分析失败")
        raise
    except Exception as exc:
        logger.error("分析请求失败: %r", exc)
        log("✗ 模型分析异常")
        raise DetectionError("检测服务暂时不可用，请稍后再试。") from exc
    log("✓ 模型返回原始结果")

    log("步骤 3/4 · 解析模型输出")
    parsed = _call_parser(raw_text)
    log("✓ 结果解析完成")

    log("步骤 4/4 · 综合品质判定")
    final_result = _to_result_dict(_call_evaluator(parsed))
    log("✓ 判定完成")

    elapsed = (datetime.now() - started).total_seconds()
    logger.info("检测完成，耗时 %.2f 秒", elapsed)
    log(f"检测完成，总耗时 {elapsed:.2f} 秒")
    return final_result

# ---------------------------------------------------------------------------
# 可选第三方组件（缺失时自动降级，不阻断页面）
# ---------------------------------------------------------------------------

try:
    from streamlit_paste_button import paste_image_button as _paste_button
except Exception:  # pragma: no cover
    _paste_button = None

try:
    from streamlit_local_storage import LocalStorage as _LocalStorage
except Exception:  # pragma: no cover
    _LocalStorage = None


OVERALL_BADGE = {
    OVERALL_PASS: ("✅", "success"),
    OVERALL_REVIEW: ("⚠️", "warning"),
    OVERALL_REJECT: ("🚫", "error"),
    OVERALL_INVALID: ("ℹ️", "info"),
}

OVERALL_COLOR = {
    OVERALL_PASS: "#16a34a",
    OVERALL_REVIEW: "#d97706",
    OVERALL_REJECT: "#dc2626",
    OVERALL_INVALID: "#64748b",
}


# ---------------------------------------------------------------------------
# 全局样式：参考 image-forensics 的深色工具台风格
# ---------------------------------------------------------------------------


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.2rem; max-width: 1200px; }
        /* 顶部标题栏 */
        .hj-header {
            display: flex; align-items: center; justify-content: space-between;
            padding: 16px 22px; border-radius: 14px; margin-bottom: 18px;
            background: linear-gradient(120deg, #0f2f24 0%, #16352a 60%, #1c4536 100%);
            border: 1px solid #23543f;
        }
        .hj-title { font-size: 22px; font-weight: 700; color: #ecfdf5; margin: 0; }
        .hj-subtitle { font-size: 13px; color: #a7d3bf; margin-top: 3px; }
        .hj-status {
            display: flex; align-items: center; gap: 8px;
            font-size: 13px; color: #d1fae5; background: rgba(0,0,0,0.25);
            padding: 8px 14px; border-radius: 999px; border: 1px solid #2f6b50;
        }
        .hj-dot { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
        .hj-dot-green { background: #22c55e; box-shadow: 0 0 8px #22c55e; animation: hj-pulse 1.8s infinite; }
        .hj-dot-red { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
        @keyframes hj-pulse { 0%{opacity:1} 50%{opacity:.45} 100%{opacity:1} }
        /* 面板标题 */
        .hj-panel-title { font-size: 15px; font-weight: 700; color: #0f766e; margin: 2px 0 10px; }
        /* 日志面板 */
        .hj-log {
            background: #0b1220; color: #7dd3fc; font-family: ui-monospace, Menlo, Consolas, monospace;
            font-size: 12.5px; line-height: 1.7; border-radius: 10px; padding: 12px 14px;
            height: 340px; overflow-y: auto; border: 1px solid #1e293b; white-space: pre-wrap;
        }
        .hj-log .ok { color: #4ade80; }
        .hj-log .err { color: #f87171; }
        .hj-log .step { color: #fbbf24; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(health: dict) -> None:
    if health.get("ok"):
        dot_class, label = "hj-dot-green", "服务正常运行中"
    else:
        dot_class, label = "hj-dot-red", "服务连接异常"
    detail = health.get("detail", "")
    checked = health.get("checked_at", "")
    st.markdown(
        f"""
        <div class="hj-header">
          <div>
            <p class="hj-title">🌿 智鉴黄精 · AI 品质检测系统</p>
            <p class="hj-subtitle">九蒸九晒黄精成品外观品质辅助评价 · 根茎完整度 / 色泽均匀度 / 霉变风险</p>
          </div>
          <div class="hj-status">
            <span class="hj-dot {dot_class}"></span>
            <span>{label}</span>
            <span style="opacity:.6">· {detail} · {checked}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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

# ---------------------------------------------------------------------------
# 检测记录：优先浏览器 localStorage 持久化，降级为 session_state
# 关键修复：历史写入与结果渲染解耦，用 result_id 去重，避免重复记录
# ---------------------------------------------------------------------------

_LS_KEY = "hj_detection_history"


def _get_ls():
    """获取 LocalStorage 实例（每会话一次）；组件缺失返回 None。"""
    if _LocalStorage is None:
        return None
    inst = st.session_state.get("_ls_instance")
    if inst is None:
        try:
            inst = _LocalStorage()
            st.session_state["_ls_instance"] = inst
        except Exception as exc:
            logger.warning("LocalStorage 初始化失败: %r", exc)
            return None
    return inst


def load_history() -> list:
    """读取历史记录：localStorage 优先，否则用 session_state。"""
    ls = _get_ls()
    if ls is not None:
        try:
            raw = ls.getItem(_LS_KEY)
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, list):
                    return data
        except Exception as exc:
            logger.warning("读取本地历史失败: %r", exc)
    return st.session_state.get("history", [])


def save_history(history: list) -> None:
    """写回历史记录到 localStorage 与 session_state。

    注意：streamlit-local-storage 的 setItem 会按 key 去重渲染，
    同一 key 在一次会话内只写一次，因此这里用自增序号保证每次写入生效。
    """
    st.session_state["history"] = history
    ls = _get_ls()
    if ls is not None:
        try:
            seq = st.session_state.get("_ls_seq", 0) + 1
            st.session_state["_ls_seq"] = seq
            ls.setItem(
                _LS_KEY,
                json.dumps(history, ensure_ascii=False),
                key=f"hj_ls_set_{seq}",
            )
        except Exception as exc:
            logger.warning("写入本地历史失败: %r", exc)


def append_history(result: dict, thumb_b64: str, result_id: str) -> None:
    """追加一条记录；同一 result_id 只写一次（修复重复记录 bug）。"""
    history = load_history()
    if any(item.get("id") == result_id for item in history):
        return
    entry = {
        "id": result_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "thumb": thumb_b64,
        "completeness": result.get("completeness"),
        "color_uniformity": result.get("color_uniformity"),
        "mold_risk": result.get("mold_risk"),
        "overall": result.get("overall", OVERALL_INVALID),
    }
    history.insert(0, entry)
    del history[HISTORY_LIMIT:]
    save_history(history)


def render_history() -> None:
    history = load_history()
    st.markdown('<div class="hj-panel-title">最近检测记录</div>', unsafe_allow_html=True)
    if not history:
        st.caption("暂无检测记录（记录已保存在你的浏览器本地，刷新不会丢失）")
        return

    header = st.columns([1.8, 2.6, 1.4, 1.4, 1.4, 1.8])
    for col, text in zip(
        header, ("检测时间", "图片", "根茎完整度", "色泽均匀度", "霉变风险", "综合评价")
    ):
        col.markdown(f"**{text}**")

    for item in history:
        row = st.columns([1.8, 2.6, 1.4, 1.4, 1.4, 1.8])
        row[0].write(item.get("time", "—"))
        if item.get("thumb"):
            try:
                row[1].image(base64.b64decode(item["thumb"]), width=88)
            except Exception:
                row[1].write("—")
        else:
            row[1].write("—")
        row[2].write(item.get("completeness") or "—")
        row[3].write(item.get("color_uniformity") or "—")
        row[4].write(item.get("mold_risk") or "—")
        overall = item.get("overall") or OVERALL_INVALID
        badge, _ = OVERALL_BADGE.get(overall, ("ℹ️", "info"))
        row[5].write(f"{badge} {overall}")

    if st.button("🗑️ 清空检测记录", key="clear_history"):
        save_history([])
        st.rerun()


# ---------------------------------------------------------------------------
# 结果展示（底部检测报告区）
# ---------------------------------------------------------------------------


def render_result(result: dict) -> None:
    st.markdown('<div class="hj-panel-title">检测报告</div>', unsafe_allow_html=True)

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

# ---------------------------------------------------------------------------
# 页面主体
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="智鉴黄精 - AI品质检测系统", page_icon="🌿", layout="wide"
)
inject_css()

# 顶部标题栏 + 真实服务状态灯
_health = probe_service_health()
render_header(_health)


def _log_lines_html() -> str:
    lines = st.session_state.get("log_lines", [])
    if not lines:
        return '<span style="opacity:.5">等待检测任务…\n上传图片后点击「开始检测」，这里会实时显示进度。</span>'
    out = []
    for ln in lines:
        cls = ""
        if ln.startswith(("✓", "检测完成")):
            cls = "ok"
        elif ln.startswith("✗"):
            cls = "err"
        elif ln.startswith("步骤"):
            cls = "step"
        out.append(f'<span class="{cls}">{ln}</span>')
    return "\n".join(out)


def _push_log(line: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.setdefault("log_lines", []).append(f"[{ts}] {line}")


def _reset_current() -> None:
    for k in ("current_image", "current_name", "last_result", "log_lines"):
        st.session_state.pop(k, None)


# 主体两栏：左=上传/操作，右=实时日志
left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown('<div class="hj-panel-title">图片上传</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "拖拽图片到此处，或点击选择（也可在下方按钮直接粘贴剪贴板图片）",
        type=list(ALLOWED_TYPES),
        help=f"支持 {'/'.join(ALLOWED_TYPES).upper()}，单张 ≤ {MAX_FILE_MB} MB；"
        "建议浅色干净背景、主体清晰，短边不低于 720 像素。",
        key="uploader",
    )

    # Ctrl+V 粘贴上传（组件可用时）
    if _paste_button is not None:
        pasted = _paste_button(
            label="📋 粘贴剪贴板图片 (Ctrl+V 后点此)",
            text_color="#ffffff",
            background_color="#0f766e",
            hover_background_color="#0d5f5a",
        )
        if getattr(pasted, "image_data", None) is not None:
            try:
                buf = io.BytesIO()
                pasted.image_data.save(buf, format="PNG")
                st.session_state["current_image"] = buf.getvalue()
                st.session_state["current_name"] = "pasted.png"
            except Exception as exc:
                logger.warning("粘贴图片处理失败: %r", exc)
                st.warning("剪贴板图片无法读取，请改用拖拽或选择文件。")
    else:
        st.caption("提示：安装 streamlit-paste-button 组件后可启用剪贴板粘贴上传。")

    # 文件上传优先覆盖当前图片
    if uploaded is not None:
        data = uploaded.getvalue()
        if len(data) > MAX_FILE_BYTES:
            st.error(f"图片超过 {MAX_FILE_MB} MB，请压缩后重新上传。")
        else:
            st.session_state["current_image"] = data
            st.session_state["current_name"] = uploaded.name

    current_image = st.session_state.get("current_image")
    if current_image:
        try:
            st.image(current_image, caption="待检测图片预览", use_container_width=True)
        except Exception:
            st.error("图片无法正常读取，请更换图片后重试。")
            st.session_state.pop("current_image", None)
            current_image = None

    # 三个操作按钮
    b1, b2, b3 = st.columns(3)
    do_detect = b1.button(
        "🔍 开始检测", type="primary", use_container_width=True, disabled=not current_image
    )
    do_reupload = b2.button("🔄 重新上传", use_container_width=True)
    do_clear = b3.button("🧹 清空", use_container_width=True)

    if do_reupload or do_clear:
        _reset_current()
        st.rerun()

with right:
    st.markdown('<div class="hj-panel-title">实时检测日志</div>', unsafe_allow_html=True)
    log_placeholder = st.empty()
    log_placeholder.markdown(
        f'<div class="hj-log">{_log_lines_html()}</div>', unsafe_allow_html=True
    )

# 执行检测：把进度实时写入右侧日志面板
if do_detect and current_image:
    st.session_state["log_lines"] = []

    def _live_log(line: str) -> None:
        _push_log(line)
        log_placeholder.markdown(
            f'<div class="hj-log">{_log_lines_html()}</div>', unsafe_allow_html=True
        )

    try:
        result = run_detection(
            current_image, st.session_state.get("current_name", "image"), _live_log
        )
        result_id = f"{int(time.time()*1000)}"
        st.session_state["last_result"] = result
        st.session_state["last_result_id"] = result_id
        st.session_state["last_thumb"] = make_thumbnail(current_image)
        # 一次性写入历史（去重），随后 rerun 让 localStorage 组件同步
        append_history(result, st.session_state["last_thumb"], result_id)
    except DetectionError as exc:
        _live_log(f"✗ {exc.user_message}")
        st.error(exc.user_message)
    except Exception:
        logger.exception("检测流程出现未预期错误")
        _live_log("✗ 未预期错误")
        st.error("检测过程中出现问题，请重新尝试；若多次失败请联系管理员。")

st.divider()

# 底部：检测报告（只渲染，不再重复写历史）
if "last_result" in st.session_state:
    render_result(st.session_state["last_result"])
    st.divider()

# 最近检测记录（浏览器本地持久化）
render_history()

