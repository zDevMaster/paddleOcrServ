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
    if margin <= 0:
        return image
    return cv2.copyMakeBorder(
        image, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )


def image_pipeline(image: np.ndarray, options: dict[str, Any] | None = None) -> np.ndarray:
    options = options or {}
    max_edge = int(options.get("maxEdge", 1600))
    return resize_max_edge(image, max_edge=max_edge)


def _rotate_by_angle(image: np.ndarray, angle: int) -> np.ndarray:
    angle = angle % 360
    if angle == 0:
        return image
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"unsupported rotate angle: {angle}")


def _prep_gray_for_orientation(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    scale = 720.0 / max(h, w)
    if scale < 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


def _top_bottom_ink_bias(bw: np.ndarray) -> float:
    """中文证件标题多在上方；用于 0° 与 180° 消歧。"""
    h = bw.shape[0]
    if h < 12:
        return 0.0
    top = float(bw[: h // 3, :].sum())
    bottom = float(bw[2 * h // 3 :, :].sum())
    total = float(bw.sum()) + 1e-6
    return (top - bottom) / total


def _document_upright_score(gray: np.ndarray) -> float:
    """综合投影方差、连通域走向、梯度与上方偏置，评估是否为正向证件图。"""
    bw = _prep_gray_for_orientation(gray)
    h, w = bw.shape[:2]

    row_sum = bw.sum(axis=1, dtype=np.float32)
    col_sum = bw.sum(axis=0, dtype=np.float32)
    row_std = float(np.std(row_sum))
    col_std = float(np.std(col_sum))
    proj_ratio = row_std / (col_std + 1e-6)

    horiz_area = 0.0
    vert_area = 0.0
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    for i in range(1, num_labels):
        _, _, ww, hh, area = stats[i]
        if area < 24 or ww < 2 or hh < 2:
            continue
        if ww >= hh * 1.15:
            horiz_area += float(area)
        elif hh >= ww * 1.15:
            vert_area += float(area)

    blur = cv2.GaussianBlur(gray if gray.shape == bw.shape else cv2.resize(gray, (w, h)), (3, 3), 0)
    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    h_energy = float(np.mean(np.abs(gx)))
    v_energy = float(np.mean(np.abs(gy))) + 1e-6

    score = (
        np.log1p(proj_ratio) * 2.2
        + np.log1p(horiz_area / (vert_area + 1e-6)) * 1.6
        + (h_energy / v_energy) * 0.25
        + _top_bottom_ink_bias(bw) * 0.8
    )
    if w >= h:
        score += 0.12
    return float(score)


def auto_correct_orientation(image: np.ndarray) -> tuple[np.ndarray, int]:
    """在 0/90/180/270 中选最像正向证件的角度（投影+连通域+上方标题偏置）。"""
    best_angle = 0
    best_score = -1e9
    for angle in (0, 90, 180, 270):
        rotated = _rotate_by_angle(image, angle)
        gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY) if rotated.ndim == 3 else rotated
        score = _document_upright_score(gray)
        if score > best_score:
            best_score = score
            best_angle = angle
    return _rotate_by_angle(image, best_angle), best_angle


def iter_document_orientations(image: np.ndarray) -> list[tuple[np.ndarray, int]]:
    """返回四向旋转候选（含原图），供低置信度时多向 OCR 重试。"""
    seen: set[tuple[int, int, int]] = set()
    variants: list[tuple[np.ndarray, int]] = []
    for angle in (0, 90, 180, 270):
        rotated = _rotate_by_angle(image, angle)
        key = rotated.shape[:2]
        if key in seen:
            continue
        seen.add(key)
        variants.append((rotated, angle))
    return variants


def to_grayscale_enhanced(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    enhanced = cv2.bilateralFilter(enhanced, d=5, sigmaColor=50, sigmaSpace=50)
    blur = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    sharpened = cv2.addWeighted(enhanced, 1.35, blur, -0.35, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def document_image_pipeline(image: np.ndarray, options: dict[str, Any] | None = None) -> np.ndarray:
    options = options or {}
    if options.get("skipEnhance"):
        img = image
        if not options.get("skipRotate"):
            img, _ = auto_correct_orientation(img)
        return image_pipeline(img, options)

    img = image
    if not options.get("skipRotate"):
        img, _ = auto_correct_orientation(img)
    img = image_pipeline(img, options)
    return to_grayscale_enhanced(img)


def idcard_image_pipeline(image: np.ndarray, options: dict[str, Any] | None = None) -> np.ndarray:
    return document_image_pipeline(image, options)
