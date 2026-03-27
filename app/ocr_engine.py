from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from paddleocr import PaddleOCR


def _resolve_path(env_name: str, fallback_relative: str) -> str:
    root = Path(__file__).resolve().parent.parent
    return str(Path(os.getenv(env_name, str(root / fallback_relative))).resolve())


def _assert_model_dirs(det_dir: str, rec_dir: str, cls_dir: str) -> None:
    for p in [det_dir, rec_dir, cls_dir]:
        if not Path(p).exists():
            raise RuntimeError(f"model dir not found: {p}")


@lru_cache(maxsize=1)
def get_ocr_engine() -> PaddleOCR:
    # 每个 worker 进程只初始化一次模型
    det_model_dir = _resolve_path("OCR_DET_MODEL_DIR", "offline_bundle/models/ch_PP-OCRv4_det_infer")
    rec_model_dir = _resolve_path("OCR_REC_MODEL_DIR", "offline_bundle/models/ch_PP-OCRv4_rec_infer")
    cls_model_dir = _resolve_path("OCR_CLS_MODEL_DIR", "offline_bundle/models/ch_ppocr_mobile_v2.0_cls_infer")
    _assert_model_dirs(det_model_dir, rec_model_dir, cls_model_dir)
    return PaddleOCR(
        use_angle_cls=True,
        lang="ch",
        det_model_dir=det_model_dir,
        rec_model_dir=rec_model_dir,
        cls_model_dir=cls_model_dir,
    )


def run_ocr(image):
    engine = get_ocr_engine()
    result = engine.ocr(image, cls=True)
    lines: list[dict] = []
    if not result:
        return lines
    for block in result:
        if not block:
            continue
        for item in block:
            if not item or len(item) < 2:
                continue
            bbox = item[0]
            text = item[1][0]
            score = float(item[1][1])
            lines.append(
                {
                    "text": text.strip(),
                    "bbox": [[float(p[0]), float(p[1])] for p in bbox],
                    "score": score,
                }
            )
    return lines

