from __future__ import annotations

import asyncio
import os
import threading
import time
import traceback
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.models import DocumentType, ImageJsonRequest, OcrResponse
from app.recognition_log import (
    KIND_DRIVER_LICENSE,
    KIND_HANDWRITING,
    KIND_IDCARD,
    KIND_VEHICLE_LICENSE,
    log_error,
    log_success,
)

_DOC_KIND = {
    DocumentType.idcard: KIND_IDCARD,
    DocumentType.vehicle_license: KIND_VEHICLE_LICENSE,
    DocumentType.driver_license: KIND_DRIVER_LICENSE,
    DocumentType.handwriting: KIND_HANDWRITING,
}
app = FastAPI(title="Intranet OCR Service", version="1.0.0")

# 单进程内的 OCR 执行互斥：同一时刻只允许一路识别（保持 1 worker，亦保护 Paddle 引擎单例）。
# 识别计算经 asyncio.to_thread 置于线程池，事件循环保持空闲，因此能在「忙」时立即拒绝新请求。
_OCR_LOCK = threading.Lock()


def _reject_when_busy() -> bool:
    """是否在识别中直接拒绝新请求（默认开启）。设 OCR_REJECT_WHEN_BUSY=0 可改回排队等待。"""
    return os.getenv("OCR_REJECT_WHEN_BUSY", "1").strip().lower() not in {"0", "false", "no", "off"}


async def _acquire_ocr_slot() -> bool:
    """获取 OCR 执行权。

    返回 True 表示已获得；返回 False 表示当前正在识别（仅「拒绝模式」会出现）。
    排队模式下在线程中阻塞等待，避免占用事件循环。
    """
    if _reject_when_busy():
        return _OCR_LOCK.acquire(blocking=False)
    await asyncio.to_thread(_OCR_LOCK.acquire)
    return True


def _busy_response(doc_type: str) -> JSONResponse:
    """服务忙：success=false 且 traceId=""，供多服务端部署时客户端切换到其它服务器。"""
    return JSONResponse(
        content={
            "success": False,
            "traceId": "",
            "elapsedMs": 0,
            "data": {"docType": doc_type, "fields": {}, "text": ""},
        }
    )


async def _load_image_from_request(request: Request, file: UploadFile | None) -> tuple:
    from app.preprocess import decode_image_from_base64, read_upload_bytes

    options = None
    if file is not None:
        content = await file.read()
        return read_upload_bytes(content), options

    try:
        body = await request.json()
        payload = ImageJsonRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid request body: {exc}") from exc
    return decode_image_from_base64(payload.imageBase64), payload.options


def _document_result_score(fields: dict[str, dict]) -> int:
    score = 0
    for item in fields.values():
        val = item.get("value")
        if val in ("", None, []):
            continue
        if isinstance(val, str):
            score += 2 if len(val) >= 4 else 1
        else:
            score += 1
    return score


def _recognize_document(doc_type: DocumentType, image, options) -> tuple[dict, str]:
    """证件类：旋转+黑白增强 OCR；偏弱时对四向旋转各试一次，取字段更完整结果。"""
    from app.extractors import extract_by_doc_type, extract_idcard, idcard_result_score
    from app.ocr_engine import run_ocr
    from app.preprocess import document_image_pipeline, image_pipeline, iter_document_orientations, to_grayscale_enhanced

    score_fn = idcard_result_score if doc_type == DocumentType.idcard else _document_result_score
    extract_fn = extract_idcard if doc_type == DocumentType.idcard else lambda lines: extract_by_doc_type(doc_type, lines)
    opts = options or {}

    def _run(img) -> tuple[dict, str, int]:
        lines = run_ocr(img, handwriting=False)
        fields, _, _, text = extract_fn(lines)
        return fields, text, score_fn(fields)

    best_fields: dict | None = None
    best_text = ""
    best_score = -1

    for img in (document_image_pipeline(image, opts), image_pipeline(image, opts)):
        fields, text, score = _run(img)
        if score > best_score:
            best_score = score
            best_fields = fields
            best_text = text
        if doc_type == DocumentType.idcard and score >= 10:
            break

    retry_threshold = 10 if doc_type == DocumentType.idcard else 8
    if best_score < retry_threshold:
        for rotated, angle in iter_document_orientations(image):
            img = to_grayscale_enhanced(image_pipeline(rotated, opts))
            fields, text, score = _run(img)
            if score > best_score:
                best_score = score
                best_fields = fields
                best_text = text

    assert best_fields is not None
    return best_fields, best_text


def _recognize_idcard_document(image, options) -> tuple[dict, str]:
    return _recognize_document(DocumentType.idcard, image, options)


def _recognize_handwriting_image(image, options) -> tuple[dict, str]:
    """手写/通用：预处理 + 手写检测参数 + extract_handwriting（CPU 密集，置于线程执行）。"""
    from app.extractors import extract_handwriting
    from app.ocr_engine import run_ocr
    from app.preprocess import ensure_min_edge, image_pipeline, pad_white_border

    image = image_pipeline(image, options)
    min_edge = int(os.getenv("OCR_HANDWRITING_MIN_EDGE", "128"))
    image = ensure_min_edge(image, min_edge=min_edge)
    pad = int(os.getenv("OCR_HANDWRITING_PAD", "28"))
    image = pad_white_border(image, margin=pad)
    lines = run_ocr(image, handwriting=True)
    fields, _, _, text = extract_handwriting(lines)
    return fields, text


def _build_response(
    trace_id: str,
    elapsed_ms: int,
    doc_type: str,
    fields: dict,
    text: str,
):
    return OcrResponse(
        success=True,
        traceId=trace_id,
        elapsedMs=elapsed_ms,
        data={
            "docType": doc_type,
            "fields": fields,
            "text": text,
        },
    )


@app.get("/health")
def health():
    return {"success": True, "status": "ok"}


@app.post("/v1/ocr/document/{doc_type}", response_model=OcrResponse)
async def ocr_document(doc_type: DocumentType, request: Request, file: UploadFile | None = File(default=None)):
    if not await _acquire_ocr_slot():
        return _busy_response(doc_type.value)
    started = time.perf_counter()
    trace_id = uuid.uuid4().hex
    kind = _DOC_KIND[doc_type]

    try:
        image, options = await _load_image_from_request(request, file)
        if doc_type == DocumentType.handwriting:
            fields, text = await asyncio.to_thread(_recognize_handwriting_image, image, options)
        else:
            fields, text = await asyncio.to_thread(_recognize_document, doc_type, image, options)
        elapsed = int((time.perf_counter() - started) * 1000)
        log_success(
            kind,
            trace_id,
            elapsed,
            {"docType": doc_type.value, "text": text, "fields": fields},
        )
        return _build_response(trace_id, elapsed, doc_type.value, fields, text)
    except HTTPException as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        log_error(
            kind,
            trace_id,
            elapsed,
            category="client_error",
            message=f"HTTP {exc.status_code} detail={exc.detail!s}",
            traceback_text=None,
        )
        raise
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        log_error(
            kind,
            trace_id,
            elapsed,
            category="exception",
            message=str(exc),
            traceback_text=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"识别过程异常: {exc!s}",
        ) from exc
    finally:
        _OCR_LOCK.release()
