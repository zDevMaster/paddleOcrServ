from __future__ import annotations

import logging
import time
from datetime import datetime
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from app.extractors import extract_by_doc_type, extract_handwriting
from app.models import DocumentType, ImageJsonRequest, OcrResponse
from app.ocr_engine import run_ocr
from app.preprocess import decode_image_from_base64, image_pipeline, read_upload_bytes

APP_DIR = Path(__file__).resolve().parent


# 只把“非 info”事件写入日志文件：识别成功/失败、程序异常等。
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")


def _logger_success(self: logging.Logger, message: str, *args, **kwargs) -> None:
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kwargs)


logging.Logger.success = _logger_success  # type: ignore[attr-defined]

LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_log_path = LOG_DIR / f"ocr_app_{datetime.now().strftime('%Y%m%d')}.log"

ocr_logger = logging.getLogger("ocr_app")
ocr_logger.setLevel(SUCCESS_LEVEL_NUM)
ocr_logger.propagate = False
if not ocr_logger.handlers:
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = RotatingFileHandler(_log_path, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8")
    fh.setLevel(SUCCESS_LEVEL_NUM)
    fh.setFormatter(fmt)
    ocr_logger.addHandler(fh)

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

    doc_type = "general"
    try:
        image, options = await _load_image_from_request(request, file)
        image = image_pipeline(image, options)

        lines = run_ocr(image)
        fields, _, _, text = extract_handwriting(lines)
        elapsed = int((time.perf_counter() - started) * 1000)
        resp = _build_response(trace_id, elapsed, doc_type, fields, text)
        ocr_logger.success(f"recognize_success traceId={trace_id} docType={doc_type} elapsedMs={elapsed}")
        return resp
    except HTTPException as exc:
        ocr_logger.warning(f"recognize_http_error traceId={trace_id} docType={doc_type} status={exc.status_code} detail={exc.detail}")
        raise
    except Exception:
        ocr_logger.exception(f"recognize_exception traceId={trace_id} docType={doc_type}")
        raise


@app.post("/v1/ocr/document/{doc_type}", response_model=OcrResponse)
async def ocr_document(doc_type: DocumentType, request: Request, file: UploadFile | None = File(default=None)):
    started = time.perf_counter()
    trace_id = uuid.uuid4().hex

    doc_type_str = doc_type.value
    try:
        image, options = await _load_image_from_request(request, file)
        image = image_pipeline(image, options)

        lines = run_ocr(image)
        fields, _, _, text = extract_by_doc_type(doc_type, lines)
        elapsed = int((time.perf_counter() - started) * 1000)
        resp = _build_response(trace_id, elapsed, doc_type_str, fields, text)
        ocr_logger.success(f"recognize_success traceId={trace_id} docType={doc_type_str} elapsedMs={elapsed}")
        return resp
    except HTTPException as exc:
        ocr_logger.warning(f"recognize_http_error traceId={trace_id} docType={doc_type_str} status={exc.status_code} detail={exc.detail}")
        raise
    except Exception:
        ocr_logger.exception(f"recognize_exception traceId={trace_id} docType={doc_type_str}")
        raise

