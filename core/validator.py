# -*- coding: utf-8 -*-
"""输入图片校验。

职责:
- 验证文件格式（JPG/JPEG/PNG）
- 验证文件大小（建议≤10MB）
- 验证分辨率（建议短边≥720px）

校验失败时返回 (False, 错误说明); 成功返回 (True, "")。
"""

import io
import os

from PIL import Image

from core.logger import get_logger

logger = get_logger(__name__)

MAX_FILE_MB = 10
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
MIN_SHORT_SIDE = 720
ALLOWED_FORMATS = ("JPEG", "PNG")
ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png")


def validate_image(image_bytes, filename=""):
    """验证上传的图片是否满足检测要求。
    
    参数:
        image_bytes: 图片二进制数据
        filename: 文件名（可选，用于格式判断）
    
    返回:
        (bool, str): (是否通过, 错误信息或空字符串)
    """
    if not image_bytes:
        return False, "图片数据为空，请重新上传。"
    
    # 文件大小检查
    size_mb = len(image_bytes) / (1024 * 1024)
    if len(image_bytes) > MAX_FILE_BYTES:
        return False, f"图片大小 {size_mb:.1f}MB 超过限制 {MAX_FILE_MB}MB，请压缩后重新上传。"
    
    # 扩展名检查（防止改扩展名伪装：内容校验在下方仍会执行）
    ext = os.path.splitext(filename or "")[1].lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        return False, f"不支持的文件格式 {ext}，仅支持 JPG/JPEG/PNG 格式。"

    # 尝试打开图片并验证格式
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        logger.warning("图片无法打开: %r", exc)
        return False, "图片格式无法识别或已损坏，请更换图片后重试。"
    
    # 格式检查（按真实文件内容判断，而非扩展名）
    img_format = img.format
    if img_format not in ALLOWED_FORMATS:
        return False, f"图片格式 {img_format} 不支持，请使用 JPG/JPEG/PNG 格式。"
    
    # 分辨率检查（建议性，不强制）
    width, height = img.size
    short_side = min(width, height)
    if short_side < MIN_SHORT_SIDE:
        logger.info(
            "图片分辨率 %dx%d 低于建议值（短边≥%dpx），可能影响检测准确性",
            width, height, MIN_SHORT_SIDE
        )
        # 不阻止检测，仅记录警告
    
    return True, ""
