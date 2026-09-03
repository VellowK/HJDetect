# -*- coding: utf-8 -*-
"""视觉模型调用层。

结构:
- VisionModel     : 抽象基类, 定义统一视觉分析接口
- DoubaoSeedModel : 通过 ARK API 调用 Doubao-Seed-2.0-lite
- DemoModel       : 演示/离线备用模式, 返回预设结果, 不调用真实 API

设计目标: 未来替换 ResNet18 时只需新增 VisionModel 子类,
UI 与业务规则 (parser/evaluator) 无需改动。

对外入口:
- 模块级 analyze_image(image_bytes, system_prompt) -> str  (app.py 编排用)
- 类级 model.analyze(image_bytes, system_prompt) -> AnalysisResult (完整管线)
"""

import base64
import json
import time

from core.config import get_mode, require_online_config
from core.logger import get_logger, sanitize
from core.parser import AnalysisResult, ParseError, parse_model_response

logger = get_logger(__name__)

REQUEST_TIMEOUT = 30          # 单次请求超时 (秒)
MAX_RETRIES = 2               # 首次请求后最多重试次数
RETRY_BACKOFF_SECONDS = 1.5   # 重试前等待


class AnalyzerError(Exception):
    """模型调用失败的统一异常。"""

    def __init__(self, message, retryable=False, cause=None):
        super().__init__(message)
        self.retryable = retryable
        self.cause = cause


class ConfigError(AnalyzerError):
    """配置缺失 (如 ARK_API_KEY 未设置)。retryable=False。"""


def _classify_http_status(status):
    """根据 HTTP 状态码分类错误: (retryable, user_message)。"""
    if status == 401:
        return False, "API Key 无效或未授权, 请检查配置。"
    if status == 403:
        return False, "没有访问该模型的权限, 请检查 API Key 与模型授权。"
    if status == 404:
        return False, "模型或接口地址不存在, 请检查 ARK_MODEL / ARK_BASE_URL 配置。"
    if status == 400:
        return False, "请求参数错误, 请检查模型名称与图片格式。"
    if status == 429:
        return True, "请求频率超限, 正在自动重试。"
    if 500 <= status < 600:
        return True, "模型服务暂时不可用, 正在自动重试。"
    return True, "API 返回异常状态码 %d, 正在自动重试。" % status


class VisionModel(object):
    """视觉模型抽象基类。

    子类必须实现 analyze(image_bytes, system_prompt) 返回 AnalysisResult。
    """

    def analyze(self, image_bytes, system_prompt=None):
        raise NotImplementedError("VisionModel 子类必须实现 analyze()")

    def shutdown(self):
        """可选的资源清理钩子, 子类按需覆盖。"""
        pass


def _encode_image_data_url(image_bytes):
    """将图片二进制编码为 data URL; 数据非法时抛 AnalyzerError。"""
    if not image_bytes or not isinstance(image_bytes, (bytes, bytearray)):
        raise AnalyzerError("图片数据为空或类型非法")
    data = bytes(image_bytes)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    else:
        raise AnalyzerError("图片数据不是有效的 JPEG/PNG 内容")
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


class DoubaoSeedModel(VisionModel):
    """通过 ARK API 调用 Doubao-Seed-2.0-lite 的视觉模型实现。

    - 超时 30 秒, 首次请求后最多自动重试 2 次
    - 确定性错误 (401/403/404/400) 不重试
    - 不记录 API Key、完整 Prompt、用户图片内容
    """

    def __init__(self, api_key=None, base_url=None, model=None):
        config = require_online_config()
        self.api_key = api_key or config["api_key"]
        self.base_url = (base_url or config["base_url"]).rstrip("/")
        self.model = model or config["model"]
        self._client = None

    def _get_client(self):
        """惰性创建 OpenAI 兼容客户端, 避免在 import 时强依赖 openai 包。"""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ConfigError("缺少 openai 依赖, 请先安装: pip install openai>=1.0")
            try:
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=REQUEST_TIMEOUT,
                    max_retries=0,  # 重试逻辑由本类统一控制
                )
            except Exception as exc:
                raise ConfigError("初始化 API 客户端失败: %s" % sanitize(str(exc)))
        return self._client

    def _build_messages(self, data_url, system_prompt):
        """构造消息体。Prompt 与图片内容不写入日志。"""
        if not system_prompt:
            from core.prompts import load_system_prompt
            system_prompt = load_system_prompt()
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": "请分析这张黄精图片, 严格按照系统指令只返回一个 JSON 对象。"},
                ],
            },
        ]

    def _call_once(self, messages):
        """执行一次 API 调用, 返回原始文本响应。"""
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                max_tokens=512,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status is None:
                status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None:
                retryable, message = _classify_http_status(int(status))
                raise AnalyzerError(message, retryable=retryable, cause=exc)
            # 网络层错误 (超时、连接失败) 视为可重试
            raise AnalyzerError("网络请求失败: %s" % sanitize(str(exc)), retryable=True, cause=exc)

        if not getattr(response, "choices", None):
            raise AnalyzerError("API 响应中没有 choices", retryable=True)
        content = getattr(response.choices[0].message, "content", None)
        if not content or not str(content).strip():
            raise AnalyzerError("API 响应内容为空", retryable=True)
        return str(content).strip()

    def analyze_raw(self, image_bytes, system_prompt=None):
        """带重试的完整请求循环, 返回模型原始文本响应。

        app.py 编排契约使用此入口; 完整管线见 analyze()。
        """
        started = time.monotonic()
        data_url = _encode_image_data_url(image_bytes)
        messages = self._build_messages(data_url, system_prompt)

        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):  # 首次 + 最多 2 次重试
            try:
                text = self._call_once(messages)
            except AnalyzerError as exc:
                last_error = exc
                if not exc.retryable:
                    logger.error("模型调用确定性失败 (attempt=%d): %s", attempt, exc)
                    raise
                logger.warning(
                    "模型调用可重试失败 (attempt=%d/%d): %s", attempt, MAX_RETRIES + 1, exc
                )
                if attempt <= MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS)
                continue

            logger.info(
                "模型调用成功 (attempt=%d, elapsed=%.2fs)", attempt, time.monotonic() - started
            )
            return text

        raise AnalyzerError(
            "模型调用失败 (已重试 %d 次): %s" % (MAX_RETRIES, last_error),
            retryable=False,
            cause=last_error,
        )

    def analyze(self, image_bytes, system_prompt=None):
        """完整管线: 图片 -> 模型 -> AnalysisResult。

        解析失败属于输出格式问题, 与请求错误共用同一重试预算。
        """
        started = time.monotonic()
        data_url = _encode_image_data_url(image_bytes)
        messages = self._build_messages(data_url, system_prompt)

        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                text = self._call_once(messages)
            except AnalyzerError as exc:
                last_error = exc
                if not exc.retryable:
                    logger.error("模型调用确定性失败 (attempt=%d): %s", attempt, exc)
                    raise
                logger.warning(
                    "模型调用可重试失败 (attempt=%d/%d): %s", attempt, MAX_RETRIES + 1, exc
                )
                if attempt <= MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS)
                continue

            try:
                result = parse_model_response(text)
            except ParseError as exc:
                logger.warning("模型输出解析失败 (attempt=%d): %s", attempt, exc)
                last_error = AnalyzerError("模型输出无法解析为合法结构", retryable=True, cause=exc)
                if attempt <= MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS)
                continue

            logger.info(
                "模型分析完成 (attempt=%d, elapsed=%.2fs)", attempt, time.monotonic() - started
            )
            return result

        raise AnalyzerError(
            "模型调用失败 (已重试 %d 次): %s" % (MAX_RETRIES, last_error),
            retryable=False,
            cause=last_error,
        )

    def health_check(self):
        """轻量连通性探测: 向模型发一个极小的文本请求, 判断 API 是否可达。

        返回 (ok: bool, detail: str)。不抛异常, 供状态指示灯周期性调用。
        仅消耗极少 token, 不涉及图片。
        """
        try:
            client = self._get_client()
            # 健康探测用短超时(6s), 避免阻塞页面加载; 与检测请求的 30s 超时区分
            probe_client = client.with_options(timeout=6.0) if hasattr(client, "with_options") else client
            response = probe_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                temperature=0,
                max_tokens=1,
            )
            if getattr(response, "choices", None):
                return True, "在线"
            return False, "响应异常"
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status is None:
                status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None:
                return False, "API 状态码 %s" % status
            return False, "连接失败: %s" % sanitize(str(exc))[:60]


class DemoModel(VisionModel):
    """演示模式: 返回预设结果, 不调用真实 API。

    仅用于演示容灾, 不得伪装为实时模型结果。
    """

    DEMO_RESULTS = [
        AnalysisResult(
            sample_valid=True,
            completeness="高",
            color_uniformity="中",
            mold_risk="低风险",
            overall="合格",
            reason="主体结构基本完整，色泽存在一定局部差异，未发现明显疑似霉变异常。",
            anomaly_description="",
        ),
        AnalysisResult(
            sample_valid=True,
            completeness="中",
            color_uniformity="低",
            mold_risk="中风险",
            overall="建议人工复核",
            reason="主体存在局部破损，色泽分布出现明显斑驳，发现局部异常特征但无法可靠区分普通色差与疑似霉变。",
            anomaly_description="黄精中段表面可见小片深色斑驳区域",
        ),
        AnalysisResult(
            sample_valid=False,
            completeness=None,
            color_uniformity=None,
            mold_risk=None,
            overall="无法评价",
            reason="未检测到能够进行可靠分析的有效黄精主体。",
            anomaly_description="",
        ),
    ]

    def __init__(self):
        self._index = 0

    def analyze(self, image_bytes, system_prompt=None):
        """返回预设结果 (轮换, 便于演示不同判定分支)。"""
        result = self.DEMO_RESULTS[self._index % len(self.DEMO_RESULTS)]
        self._index += 1
        logger.info("Demo 模式: 返回预设结果 #%d", self._index)
        return result


_model_instance = None


def health_check():
    """模块级健康探测入口, 供 UI 状态指示灯调用。

    - online 模式: 真实探测 ARK API 连通性
    - demo 模式: 视为始终在线
    返回 (ok: bool, detail: str)。
    """
    try:
        model = _get_model()
    except Exception as exc:
        return False, "配置错误: %s" % sanitize(str(exc))[:60]
    if isinstance(model, DemoModel):
        return True, "演示模式"
    checker = getattr(model, "health_check", None)
    if callable(checker):
        return checker()
    return False, "不支持健康检查"


def _get_model():
    """创建并复用模型实例; 运行模式在进程内保持一致。"""
    global _model_instance
    if _model_instance is None:
        _model_instance = create_model()
    return _model_instance


def analyze_image(image_bytes, system_prompt=None):
    """模块级入口 (app.py 编排契约): 图片字节 -> 模型原始文本响应。

    demo 模式将预设结果序列化为 JSON 文本, 使后续 parser/evaluator
    流程与在线模式完全一致。
    """
    model = _get_model()
    if isinstance(model, DemoModel):
        result = model.analyze(image_bytes)
        return json.dumps(result.to_dict(), ensure_ascii=False)
    return model.analyze_raw(image_bytes, system_prompt)


def create_model(mode=None):
    """根据 APP_MODE 创建模型实例。"""
    mode = (mode or get_mode()).lower()
    if mode == "demo":
        return DemoModel()
    if mode == "online":
        return DoubaoSeedModel()
    raise ConfigError("未知运行模式: %s" % mode)
