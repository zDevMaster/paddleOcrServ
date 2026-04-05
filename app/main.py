from __future__ import annotations

import os
import time
import traceback
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from app.extractors import extract_by_doc_type, extract_handwriting
from app.models import DocumentType, ImageJsonRequest, OcrResponse
from app.ocr_engine import run_ocr
from app.preprocess import (
    decode_image_from_base64,
    ensure_min_edge,
    image_pipeline,
    pad_white_border,
    read_upload_bytes,
)
from app.recognition_log import (
    KIND_DRIVER_LICENSE,
    KIND_HANDWRITING,
    KIND_IDCARD,
    KIND_VEHICLE_LICENSE,
    log_error,
    log_success,
)
from app.service_log import install_uvicorn_file_mirror

_DOC_KIND = {
    DocumentType.idcard: KIND_IDCARD,
    DocumentType.vehicle_license: KIND_VEHICLE_LICENSE,
    DocumentType.driver_license: KIND_DRIVER_LICENSE,
    DocumentType.handwriting: KIND_HANDWRITING,
}

# `/v1/ocr/general` 与 `/v1/ocr/document/handwriting` 共用同一套流水线，响应 data.docType 统一为该值。
HANDWRITING_RESPONSE_DOC_TYPE = "handwriting"

app = FastAPI(title="Intranet OCR Service", version="1.0.0")


async def _load_image_from_request(request: Request, file: UploadFile | None) -> tuple:
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


async def _recognize_handwriting_from_request(
    request: Request,
    file: UploadFile | None,
) -> tuple[dict, str]:
    """与 `/v1/ocr/document/handwriting` 相同：预处理 + 手写检测参数 + extract_handwriting。"""
    image, options = await _load_image_from_request(request, file)
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


@app.post("/v1/ocr/general", response_model=OcrResponse)
async def ocr_general(request: Request, file: UploadFile | None = File(default=None)):
    started = time.perf_counter()
    trace_id = uuid.uuid4().hex
    kind = KIND_HANDWRITING

    try:
        fields, text = await _recognize_handwriting_from_request(request, file)
        elapsed = int((time.perf_counter() - started) * 1000)
        log_success(
            kind,
            trace_id,
            elapsed,
            {"docType": HANDWRITING_RESPONSE_DOC_TYPE, "text": text, "fields": fields},
        )
        return _build_response(trace_id, elapsed, HANDWRITING_RESPONSE_DOC_TYPE, fields, text)
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


@app.post("/v1/ocr/document/{doc_type}", response_model=OcrResponse)
async def ocr_document(doc_type: DocumentType, request: Request, file: UploadFile | None = File(default=None)):
    started = time.perf_counter()
    trace_id = uuid.uuid4().hex
    kind = _DOC_KIND[doc_type]

    try:
        if doc_type == DocumentType.handwriting:
            fields, text = await _recognize_handwriting_from_request(request, file)
        else:
            image, options = await _load_image_from_request(request, file)
            image = image_pipeline(image, options)
            lines = run_ocr(image, handwriting=False)
            fields, _, _, text = extract_by_doc_type(doc_type, lines)
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


install_uvicorn_file_mirror()
