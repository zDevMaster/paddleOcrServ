from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field


APP_DIR = Path(__file__).resolve().parent
SITE_DIR = APP_DIR / "site"
DATA_DIR = APP_DIR / "data"
DEFAULT_OCR_BASE = "http://127.0.0.1:8000"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DOC_TO_DIR = {
    "idcard": "idcard",
    "vehicle_license": "VehicleLicense",
    "driver_license": "DrivingLicense",
}

app = FastAPI(title="OCR Batch Test Site", version="2.0.0")


class BatchRequest(BaseModel):
    docType: str = Field(..., description="idcard/vehicle_license/driver_license")
    batchSize: int = Field(10, description="5-100")
    ocrBase: str = Field(DEFAULT_OCR_BASE)


def _doc_folder(doc_type: str) -> Path:
    if doc_type not in DOC_TO_DIR:
        raise HTTPException(status_code=400, detail="docType must be idcard/vehicle_license/driver_license")
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
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"call ocr failed: {exc}") from exc


@app.post("/api/batch/run")
async def api_batch_run(req: BatchRequest):
    doc_type = req.docType.strip()
    batch_size = max(5, min(100, int(req.batchSize)))
    ocr_base = req.ocrBase.rstrip("/")

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
                    failed.append({"file": img.name, "error": resp.text[:500]})
                    continue
                data = resp.json()
                jp = _json_path_for(img)
                jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                processed.append(img.name)
            except Exception as exc:
                failed.append({"file": img.name, "error": str(exc)})

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

