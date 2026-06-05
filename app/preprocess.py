from __future__ import annotations

import base64
from typing import Any

import cv2
import numpy as np


def decode_image_from_base64(image_base64: str) -> np.ndarray:
    raw = base64.b64decode(image_base64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("invalid image base64")
    return image


def read_upload_bytes(content: bytes) -> np.ndarray:
    arr = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("invalid upload image")
    return image


def resize_max_edge(image: np.ndarray, max_edge: int = 1600) -> np.ndarray:
    h, w = image.shape[:2]
    edge = max(h, w)
    if edge <= max_edge:
        return image
    scale = max_edge / float(edge)
    nw, nh = int(w * scale), int(h * scale)
    return cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)


def compute_quality(image: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_score = max(0.0, min(1.0, blur / 300.0))

    reflection_pixels = float((gray > 245).sum())
    reflection_ratio = reflection_pixels / float(gray.size)
    reflection_score = max(0.0, min(1.0, 1.0 - reflection_ratio * 8.0))

    edges = cv2.Canny(gray, 80, 200)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
    tilt_deg = 0.0
    if lines is not None and len(lines) > 0:
        angles = []
        for item in lines[:50]:
            theta = item[0][1]
            angle = abs((theta * 180.0 / np.pi) - 90.0)
            angles.append(min(angle, abs(180 - angle)))
        if angles:
            tilt_deg = float(np.median(angles))
    tilt_score = max(0.0, min(1.0, 1.0 - tilt_deg / 30.0))

    overall = round((blur_score * 0.45 + reflection_score * 0.3 + tilt_score * 0.25), 4)
    return {
        "blurScore": round(blur_score, 4),
        "reflectionScore": round(reflection_score, 4),
        "tiltScore": round(tilt_score, 4),
        "overall": overall,
    }


def ensure_min_edge(image: np.ndarray, min_edge: int) -> np.ndarray:
    """过小的手写图有效像素少，识别易把形近字混淆（如 四/团）；按比例放大后再走检测与识别。"""
    if min_edge <= 0:
        return image
    h, w = image.shape[:2]
    edge = max(h, w)
    if edge >= min_edge:
        return image
    scale = min_edge / float(edge)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    return cv2.resize(image, (nw, nh), interpolation=cv2.INTER_CUBIC)


def pad_white_border(image: np.ndarray, margin: int = 28) -> np.ndarray:
    """手写/签名常贴边，四周加白边有利于检测框完整包住笔画。"""
    if margin <= 0:
        return image
    return cv2.copyMakeBorder(
        image, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )


def image_pipeline(image: np.ndarray, options: dict[str, Any] | None = None) -> np.ndarray:
    options = options or {}
    max_edge = int(options.get("maxEdge", 1600))
    return resize_max_edge(image, max_edge=max_edge)


def idcard_image_pipeline(image: np.ndarray, options: dict[str, Any] | None = None) -> np.ndarray:
    """身份证等证件扫描件：缩放后转灰度、CLAHE 增强对比度并轻锐化，提高低对比/偏色图的 OCR 识别率。"""
    options = options or {}
    if options.get("skipEnhance"):
        return image_pipeline(image, options)
    img = image_pipeline(image, options)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    enhanced = cv2.bilateralFilter(enhanced, d=5, sigmaColor=50, sigmaSpace=50)
    blur = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    sharpened = cv2.addWeighted(enhanced, 1.35, blur, -0.35, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)

