from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

import numpy as np
from paddleocr import PaddleOCR


def _resolve_path(env_name: str, fallback_relative: str) -> str:
    root = Path(__file__).resolve().parent.parent
    return str(Path(os.getenv(env_name, str(root / fallback_relative))).resolve())


def _assert_model_dirs(*dirs: str) -> None:
    for p in dirs:
        if not Path(p).exists():
            raise RuntimeError(f"model dir not found: {p}")


@lru_cache(maxsize=1)
def get_ocr_engine() -> PaddleOCR:
    # 每个 worker 进程只初始化一次模型。
    # PaddleOCR 3.x / PaddleX 需要各目录内含 inference.yml；旧版仅含 pdmodel 的包不可用。
    # 关闭文本行方向分类，避免依赖仅有旧权重的 cls 目录。
    det_model_dir = _resolve_path(
        "OCR_DET_MODEL_DIR",
        "offline_bundle/models/PP-OCRv4_mobile_det_infer",
    )
    rec_model_dir = _resolve_path(
        "OCR_REC_MODEL_DIR",
        "offline_bundle/models/PP-OCRv4_mobile_rec_infer",
    )
    _assert_model_dirs(det_model_dir, rec_model_dir)
    return PaddleOCR(
        # 使用 PaddleX 推理包（inference.yml）时，textline orientation 由 PaddleOCR 参数控制；
        # 这里直接显式关闭，避免额外 cls 相关模型加载。
        # 离线稳定性：关闭文档方向分类/版面矫正/行方向分类，避免在初始化阶段加载额外官方模型。
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_detection_model_name="PP-OCRv4_mobile_det",
        text_detection_model_dir=det_model_dir,
        text_recognition_model_name="PP-OCRv4_mobile_rec",
        text_recognition_model_dir=rec_model_dir,
        # 规避部分 Paddle CPU + oneDNN(PIR) 组合下的 NotImplementedError
        enable_mkldnn=False,
    )


def _poly_from_rec_boxes(box: np.ndarray) -> list[list[float]]:
    """将 rec_boxes 一行转为四点框（与旧版 det 多边形格式一致）。"""
    b = np.asarray(box, dtype=float).reshape(-1)
    if b.size >= 8:
        return [[float(b[i]), float(b[i + 1])] for i in range(0, 8, 2)]
    if b.size >= 4:
        x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]


def run_ocr(image):
    engine = get_ocr_engine()
    chunks = engine.predict(image)
    lines: list[dict] = []
    for chunk in chunks or []:
        data = dict(chunk) if hasattr(chunk, "keys") else chunk
        texts = data.get("rec_texts") or []
        scores = data.get("rec_scores") or []
        polys = data.get("rec_polys") or []
        boxes = data.get("rec_boxes")
        for i, text in enumerate(texts):
            st = str(text).strip()
            if not st:
                continue
            score = float(scores[i]) if i < len(scores) else 0.0
            if i < len(polys) and polys[i] is not None:
                bbox = [[float(p[0]), float(p[1])] for p in np.asarray(polys[i])]
            elif boxes is not None and len(np.asarray(boxes)) > i:
                bbox = _poly_from_rec_boxes(np.asarray(boxes)[i])
            else:
                bbox = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
            lines.append({"text": st, "bbox": bbox, "score": score})
    return lines

