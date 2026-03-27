from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from app.extractors import extract_by_doc_type, extract_handwriting
from app.models import DocumentType, ImageJsonRequest, OcrResponse
from app.ocr_engine import run_ocr
from app.preprocess import decode_image_from_base64, image_pipeline, read_upload_bytes

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

    image, options = await _load_image_from_request(request, file)
    image = image_pipeline(image, options)

    lines = run_ocr(image)
    fields, _, _, text = extract_handwriting(lines)
    elapsed = int((time.perf_counter() - started) * 1000)
    return _build_response(trace_id, elapsed, "general", fields, text)


@app.post("/v1/ocr/document/{doc_type}", response_model=OcrResponse)
async def ocr_document(doc_type: DocumentType, request: Request, file: UploadFile | None = File(default=None)):
    started = time.perf_counter()
    trace_id = uuid.uuid4().hex

    image, options = await _load_image_from_request(request, file)
    image = image_pipeline(image, options)

    lines = run_ocr(image)
    fields, _, _, text = extract_by_doc_type(doc_type, lines)
    elapsed = int((time.perf_counter() - started) * 1000)
    return _build_response(trace_id, elapsed, doc_type.value, fields, text)

