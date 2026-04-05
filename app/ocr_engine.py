from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

# 部分环境下 Paddle 3.x + oneDNN 推理会触发未实现分支；在 import paddle 之前设置最稳妥。
os.environ.setdefault("FLAGS_use_mkldnn", "0")

if TYPE_CHECKING:
    from paddleocr import PaddleOCR


def _resolve_path(env_name: str, fallback_relative: str) -> str:
    root = Path(__file__).resolve().parent.parent
    return str(Path(os.getenv(env_name, str(root / fallback_relative))).resolve())


def _assert_paddlex_infer_dir(path: str) -> None:
    p = Path(path)
    if not p.is_dir():
        raise RuntimeError(f"model dir not found: {path}")
    for fn in ("inference.yml", "inference.pdiparams", "inference.json"):
        if not (p / fn).is_file():
            raise RuntimeError(f"model file missing: {p / fn}（请运行 scripts/download_models.py 下载 PaddleX 推理包）")


@lru_cache(maxsize=1)
def get_ocr_engine() -> "PaddleOCR":
    """PaddleOCR 3.x（PaddleX）：须使用带 inference.yml 的官方推理目录，见 offline_bundle/models/。

    **不在模块顶层 import paddleocr**，避免阻塞 uvicorn 绑定端口；首次识别时再加载（/health 可立刻响应）。

    模型由环境变量选择（与 startupV4m.bat / startupv5m.bat / startupv5s.bat 一致）：
    - ``OCR_DET_MODEL_NAME`` / ``OCR_REC_MODEL_NAME``：PaddleX 模型名，如 ``PP-OCRv5_server_det``。
    - ``OCR_DET_MODEL_DIR`` / ``OCR_REC_MODEL_DIR``：推理目录；未设置时默认为
      ``offline_bundle/models/<模型名>_infer``。
    """
    from paddleocr import PaddleOCR

    det_name = os.getenv("OCR_DET_MODEL_NAME", "PP-OCRv5_server_det").strip()
    rec_name = os.getenv("OCR_REC_MODEL_NAME", "PP-OCRv5_server_rec").strip()
    det_dir = _resolve_path("OCR_DET_MODEL_DIR", f"offline_bundle/models/{det_name}_infer")
    rec_dir = _resolve_path("OCR_REC_MODEL_DIR", f"offline_bundle/models/{rec_name}_infer")
    _assert_paddlex_infer_dir(det_dir)
    _assert_paddlex_infer_dir(rec_dir)

    return PaddleOCR(
        use_textline_orientation=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        enable_mkldnn=False,
        text_detection_model_name=det_name,
        text_detection_model_dir=det_dir,
        text_recognition_model_name=rec_name,
        text_recognition_model_dir=rec_dir,
    )


def _predict_kw_handwriting() -> dict:
    """手写连笔、细笔画：略放宽检测阈值；可用环境变量微调。"""
    return {
        "text_det_thresh": float(os.getenv("OCR_HANDWRITING_DET_THRESH", "0.2")),
        "text_det_box_thresh": float(os.getenv("OCR_HANDWRITING_BOX_THRESH", "0.35")),
        "text_det_unclip_ratio": float(os.getenv("OCR_HANDWRITING_UNCLIP", "2.0")),
        "text_rec_score_thresh": float(os.getenv("OCR_HANDWRITING_REC_THRESH", "0.0")),
    }


def run_ocr(image: np.ndarray, *, handwriting: bool = False) -> list[dict]:
    """返回与旧版一致的行列表：text / bbox / score。

    handwriting=True 时（通用 OCR / 手写）使用略敏感的检测参数，减轻漏检与贴边截断；
    证件类扫描件保持默认参数。
    """
    engine = get_ocr_engine()
    kw = _predict_kw_handwriting() if handwriting else {}
    outputs = engine.predict(image, **kw)
    if not outputs:
        return []
    res = outputs[0]
    texts = res.get("rec_texts") or []
    scores = res.get("rec_scores") or []
    polys = res.get("rec_polys") or []
    lines: list[dict] = []
    for i, text in enumerate(texts):
        score = float(scores[i]) if i < len(scores) else 0.0
        poly = polys[i] if i < len(polys) else None
        if poly is None:
            bbox = []
        else:
            arr = np.asarray(poly, dtype=np.float64).reshape(-1, 2)
            bbox = [[float(p[0]), float(p[1])] for p in arr]
        t = str(text).strip() if text is not None else ""
        lines.append(
            {
                "text": t,
                "bbox": bbox,
                "score": score,
            }
        )
    return lines
