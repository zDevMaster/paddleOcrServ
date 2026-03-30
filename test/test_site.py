from __future__ import annotations

import logging
import json
import time
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field


APP_DIR = Path(__file__).resolve().parent
SITE_DIR = APP_DIR / "site"
DATA_DIR = APP_DIR / "data"
LOG_DIR = APP_DIR / "logs"
DEFAULT_OCR_BASE = "http://127.0.0.1:8000"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DOC_TO_DIR = {
    "idcard": "idcard",
    "vehicle_license": "VehicleLicense",
    "driver_license": "DrivingLicense",
    "handwriting": "HandWrite",
}

app = FastAPI(title="OCR Batch Test Site", version="2.0.0")

# 只把“非 info”事件写入文件：识别成功/失败、程序异常等
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")


def _logger_success(self: logging.Logger, message: str, *args, **kwargs) -> None:
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kwargs)


logging.Logger.success = _logger_success  # type: ignore[attr-defined]

LOG_DIR.mkdir(parents=True, exist_ok=True)
_log_path = LOG_DIR / f"test_site_{datetime.now().strftime('%Y%m%d')}.log"
test_logger = logging.getLogger("ocr_test_site")
test_logger.setLevel(SUCCESS_LEVEL_NUM)
test_logger.propagate = False
fmt = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
fh = RotatingFileHandler(_log_path, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8")
fh.setLevel(SUCCESS_LEVEL_NUM)
fh.setFormatter(fmt)

# uvicorn 可能会预先给某些 logger 配置 handlers；为了确保日志一定落到文件，清空旧 handlers 后重新挂载。
for h in list(test_logger.handlers):
    test_logger.removeHandler(h)
test_logger.addHandler(fh)


class BatchRequest(BaseModel):
    docType: str = Field(..., description="idcard/vehicle_license/driver_license")
    batchSize: int = Field(10, description="5-100")
    ocrBase: str = Field(DEFAULT_OCR_BASE)


def _doc_folder(doc_type: str) -> Path:
    if doc_type not in DOC_TO_DIR:
        raise HTTPException(
            status_code=400,
            detail="docType must be idcard/vehicle_license/driver_license/handwriting",
        )
    folder = DATA_DIR / DOC_TO_DIR[doc_type]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _image_files(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    files.sort(key=lambda p: p.name.lower())
    return files


def _json_path_for(img_path: Path) -> Path:
    return img_path.with_suffix(".json")


def _page_path(name: str) -> Path:
    return SITE_DIR / name


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _image_url(doc_type: str, filename: str) -> str:
    return f"/api/image/{doc_type}/{filename}"


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _read_text(_page_path("index.html"))


@app.get("/batch/idcard", response_class=HTMLResponse)
def page_idcard() -> str:
    return _read_text(_page_path("batch_idcard.html"))


@app.get("/batch/vehicle_license", response_class=HTMLResponse)
def page_vehicle() -> str:
    return _read_text(_page_path("batch_vehicle_license.html"))


@app.get("/batch/driver_license", response_class=HTMLResponse)
def page_driver() -> str:
    return _read_text(_page_path("batch_driver_license.html"))


@app.get("/test/handwriting", response_class=HTMLResponse)
def page_handwriting() -> str:
    return _read_text(_page_path("handwriting.html"))


@app.get("/api/image/{doc_type}/{filename}")
def api_image(doc_type: str, filename: str):
    folder = _doc_folder(doc_type)
    target = folder / filename
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(target)


@app.get("/api/health")
async def api_health(ocrBase: str = DEFAULT_OCR_BASE):
    url = f"{ocrBase.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            return {"success": resp.status_code == 200, "status_code": resp.status_code, "body": resp.json()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.post("/api/recognize")
async def api_recognize(
    file: UploadFile = File(...),
    docType: str = Form(...),
    ocrBase: str = Form(DEFAULT_OCR_BASE),
):
    doc_type = (docType or "").strip()
    ocr_base = (ocrBase or DEFAULT_OCR_BASE).rstrip("/")
    if not doc_type:
        raise HTTPException(status_code=400, detail="docType is required")
    req_trace = uuid.uuid4().hex

    if doc_type == "handwriting":
        target = f"{ocr_base}/v1/ocr/general"
    elif doc_type in {"idcard", "vehicle_license", "driver_license"}:
        target = f"{ocr_base}/v1/ocr/document/{doc_type}"
    else:
        raise HTTPException(status_code=400, detail="docType must be one of idcard/vehicle_license/driver_license/handwriting")

    content = await file.read()
    files = {"file": (file.filename or "upload.jpg", content, file.content_type or "application/octet-stream")}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, files=files)
            if resp.status_code >= 400:
                err_snip = (resp.text or "")[:300]
                test_logger.warning(
                    f"recognize_failed reqTrace={req_trace} docType={doc_type} status={resp.status_code} error_snip={err_snip}"
                )
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            data = resp.json()
            test_logger.success(
                f"recognize_success reqTrace={req_trace} docType={doc_type} ocrTraceId={data.get('traceId')} elapsedMs={data.get('elapsedMs')}"
            )
            return data
    except HTTPException:
        # 400/500 这类会在上面已经记录；这里不重复写栈信息
        raise
    except Exception as exc:
        test_logger.exception(f"recognize_exception reqTrace={req_trace} docType={doc_type} err={exc}")
        raise HTTPException(status_code=500, detail=f"call ocr failed: {exc}") from exc


@app.post("/api/handwrite/save")
async def api_handwrite_save(
    file: UploadFile = File(...),
    ocrBase: str = Form(DEFAULT_OCR_BASE),
):
    """手写图片识别，并将 PNG 与识别结果 JSON 保存到 test/data/HandWrite。"""
    ocr_base = (ocrBase or DEFAULT_OCR_BASE).rstrip("/")
    target = f"{ocr_base}/v1/ocr/general"
    req_trace = uuid.uuid4().hex
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    files = {"file": (file.filename or "handwrite.png", content, file.content_type or "application/octet-stream")}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, files=files)
            if resp.status_code >= 400:
                err_snip = (resp.text or "")[:300]
                test_logger.warning(
                    f"handwrite_failed reqTrace={req_trace} status={resp.status_code} error_snip={err_snip}"
                )
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            data = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        test_logger.exception(f"handwrite_exception reqTrace={req_trace} err={exc}")
        raise HTTPException(status_code=500, detail=f"call ocr failed: {exc}") from exc

    folder = _doc_folder("handwriting")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    base_name = f"{stamp}_{uid}"
    png_path = folder / f"{base_name}.png"
    json_path = folder / f"{base_name}.json"

    png_path.write_bytes(content)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    test_logger.success(
        f"handwrite_saved reqTrace={req_trace} baseName={base_name} ocrTraceId={data.get('traceId')} elapsedMs={data.get('elapsedMs')}"
    )
    return {
        "success": True,
        "baseName": base_name,
        "savedImage": str(png_path.relative_to(APP_DIR)).replace("\\", "/"),
        "savedJson": str(json_path.relative_to(APP_DIR)).replace("\\", "/"),
        "imageUrl": _image_url("handwriting", f"{base_name}.png"),
        "data": data,
    }


@app.post("/api/batch/run")
async def api_batch_run(req: BatchRequest):
    started = time.perf_counter()
    doc_type = req.docType.strip()
    batch_size = max(5, min(100, int(req.batchSize)))
    ocr_base = req.ocrBase.rstrip("/")
    batch_trace = uuid.uuid4().hex

    folder = _doc_folder(doc_type)
    images = _image_files(folder)
    pending = [p for p in images if not _json_path_for(p).exists()]
    to_process = pending[:batch_size]

    target = f"{ocr_base}/v1/ocr/document/{doc_type}"
    processed = []
    failed = []
    async with httpx.AsyncClient(timeout=120) as client:
        for img in to_process:
            try:
                with img.open("rb") as f:
                    files = {"file": (img.name, f.read(), "application/octet-stream")}
                resp = await client.post(target, files=files)
                if resp.status_code >= 400:
                    err_snip = (resp.text or "")[:500]
                    failed.append({"file": img.name, "error": err_snip})
                    test_logger.warning(
                        f"batch_item_failed batchTrace={batch_trace} docType={doc_type} file={img.name} status={resp.status_code} error_snip={err_snip[:300]}"
                    )
                    continue
                data = resp.json()
                jp = _json_path_for(img)
                jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                processed.append(img.name)
            except Exception as exc:
                failed.append({"file": img.name, "error": str(exc)})
                test_logger.exception(
                    f"batch_item_exception batchTrace={batch_trace} docType={doc_type} file={img.name} err={exc}"
                )

    elapsed = int((time.perf_counter() - started) * 1000)
    test_logger.success(
        f"batch_run_done batchTrace={batch_trace} docType={doc_type} requestedBatchSize={req.batchSize} actualBatchSize={batch_size} processedCount={len(processed)} failedCount={len(failed)} elapsedMs={elapsed}"
    )
    return {
        "success": True,
        "docType": doc_type,
        "requestedBatchSize": req.batchSize,
        "actualBatchSize": batch_size,
        "totalImages": len(images),
        "pendingBeforeRun": len(pending),
        "processedCount": len(processed),
        "failedCount": len(failed),
        "processedFiles": processed,
        "failedFiles": failed,
        "pendingAfterRun": max(0, len(pending) - len(processed)),
    }


@app.get("/api/batch/results")
def api_batch_results(
    docType: str = Query(...),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=5, le=100),
):
    doc_type = docType.strip()
    folder = _doc_folder(doc_type)
    images = _image_files(folder)
    total = len(images)
    start = (page - 1) * pageSize
    end = start + pageSize
    page_items = images[start:end]

    items = []
    for img in page_items:
        jp = _json_path_for(img)
        exists = jp.exists()
        json_text = ""
        if exists:
            try:
                json_text = jp.read_text(encoding="utf-8")
            except Exception as exc:
                json_text = json.dumps({"read_error": str(exc)}, ensure_ascii=False)
        items.append(
            {
                "fileName": img.name,
                "imageUrl": _image_url(doc_type, img.name),
                "jsonExists": exists,
                "jsonText": json_text,
            }
        )

    recognized = 0
    for img in images:
        if _json_path_for(img).exists():
            recognized += 1

    return {
        "success": True,
        "docType": doc_type,
        "page": page,
        "pageSize": pageSize,
        "total": total,
        "recognized": recognized,
        "unrecognized": total - recognized,
        "items": items,
    }

