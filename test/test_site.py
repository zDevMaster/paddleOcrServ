from __future__ import annotations

import json
import uuid
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
    "handwriting": "HandWrite",
}

app = FastAPI(title="OCR Batch Test Site", version="2.0.0")


async def _require_ocr_service(ocr_base: str) -> None:
    """调用 OCR 接口前先探测 /health；未启动则返回 503 与明确中文说明。"""
    base = (ocr_base or DEFAULT_OCR_BASE).rstrip("/")
    url = f"{base}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"无法连接 OCR 微服务（{base}）。请先在项目根目录执行 startup.bat（或 uvicorn）"
                f"启动服务后再试。连接错误: {exc}"
            ),
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=503,
            detail=f"连接 OCR 微服务超时（{url}）。请确认 {base} 已启动且未被防火墙拦截。",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"检查 OCR 微服务时出错: {exc}",
        ) from exc

    if resp.status_code != 200:
        raise HTTPException(
            status_code=503,
            detail=(
                f"OCR 微服务未就绪：GET /health 返回 HTTP {resp.status_code}。"
                f"请确认微服务已启动（默认 http://127.0.0.1:8000）。"
            ),
        )
    try:
        body = resp.json()
        if isinstance(body, dict) and body.get("success") is False:
            raise HTTPException(
                status_code=503,
                detail=f"OCR 微服务 /health 未返回成功: {body}",
            )
    except HTTPException:
        raise
    except Exception:
        pass


class BatchRequest(BaseModel):
    docType: str = Field(..., description="idcard/vehicle_license/driver_license/handwriting")
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


def _html_page(name: str) -> HTMLResponse:
    """静态页统一 UTF-8，避免浏览器按系统默认编码误判。"""
    return HTMLResponse(
        content=_read_text(_page_path(name)),
        media_type="text/html; charset=utf-8",
    )


def _image_url(doc_type: str, filename: str) -> str:
    return f"/api/image/{doc_type}/{filename}"


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return _html_page("index.html")


@app.get("/batch/idcard", response_class=HTMLResponse)
def page_idcard() -> HTMLResponse:
    return _html_page("batch_idcard.html")


@app.get("/batch/vehicle_license", response_class=HTMLResponse)
def page_vehicle() -> HTMLResponse:
    return _html_page("batch_vehicle_license.html")


@app.get("/batch/driver_license", response_class=HTMLResponse)
def page_driver() -> HTMLResponse:
    return _html_page("batch_driver_license.html")


@app.get("/batch/handwriting", response_class=HTMLResponse)
def page_handwriting() -> HTMLResponse:
    return _html_page("batch_handwriting.html")


@app.post("/api/handwriting/submit")
async def api_handwriting_submit(
    file: UploadFile = File(...),
    ocrBase: str = Form(DEFAULT_OCR_BASE),
):
    """画布手写签名：保存为 test/data/HandWrite/{uuid}.png，调用 /v1/ocr/general，写回同名 .json。"""
    ocr_base = (ocrBase or DEFAULT_OCR_BASE).rstrip("/")
    content = await file.read()
    await _require_ocr_service(ocr_base)

    folder = DATA_DIR / "HandWrite"
    folder.mkdir(parents=True, exist_ok=True)
    guid = uuid.uuid4().hex
    img_path = folder / f"{guid}.png"
    img_path.write_bytes(content)

    target = f"{ocr_base}/v1/ocr/general"
    files = {"file": (img_path.name, content, file.content_type or "image/png")}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, files=files)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"call ocr failed: {exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"invalid ocr json: {exc}") from exc

    jp = img_path.with_suffix(".json")
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "guid": guid,
        "fileName": img_path.name,
        "jsonPath": str(jp.relative_to(APP_DIR)).replace("\\", "/"),
        "ocr": data,
    }


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

    await _require_ocr_service(ocr_base)

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

    await _require_ocr_service(ocr_base)

    folder = _doc_folder(doc_type)
    images = _image_files(folder)
    pending = [p for p in images if not _json_path_for(p).exists()]
    to_process = pending[:batch_size]

    if doc_type == "handwriting":
        target = f"{ocr_base}/v1/ocr/general"
    else:
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

