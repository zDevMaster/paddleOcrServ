from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
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

log = logging.getLogger("test_site")


def _ocr_upstream_timeout() -> httpx.Timeout:
    """调用 OCR 微服务：首请求可能加载模型（可达数分钟），默认 600s。

    环境变量 ``OCR_UPSTREAM_TIMEOUT`` 可改为更大（秒），例如 ``1200``。
    """
    sec = float(os.getenv("OCR_UPSTREAM_TIMEOUT", "600"))
    if sec < 30:
        sec = 30.0
    return httpx.Timeout(sec, connect=min(60.0, sec))


def _ocr_request_error_detail(exc: BaseException, target: str) -> str:
    """把 httpx 异常转成对用户可读的中文说明（含常见首包超时）。"""
    name = type(exc).__name__
    msg = str(exc)
    extra = ""
    if "ReadTimeout" in name or "read timed out" in msg.lower():
        extra = (
            "常见原因：OCR 正在首次加载模型（CPU 上可能需数分钟），测试站等待超时。"
            "请在运行测试站的终端执行 set OCR_UPSTREAM_TIMEOUT=1200 后重启测试站，"
            "或在 OCR 服务器本机浏览器先访问一次 /v1/ocr/general 完成预热。"
        )
    elif "ReadError" in name or "RemoteProtocolError" in name:
        extra = (
            "常见原因：读响应时连接被对端关闭——多见于 OCR 推理中进程崩溃（如内存不足 OOM）、"
            "worker 被系统终止、或推理过久导致连接异常。请查看运行启动脚本（如 startupv5s.bat）的窗口是否有 Python 报错；"
            "可尝试启动前 set OCR_WORKERS=1 降低内存占用，并在本机先单独调用一次 /v1/ocr/general 完成预热。"
            "测试站会对 ReadError 自动重试（次数由 OCR_POST_RETRIES 控制，默认 2 次重试）。"
        )
    elif "ConnectTimeout" in name or "ConnectError" in name:
        extra = "无法建立到 OCR 的 TCP 连接，请确认 OCR 进程仍存活且防火墙放行。"
    return (
        f"调用 OCR 识别接口失败（{name}）。{extra} "
        f"{_ocr_upstream_network_hint()} 目标: {target}。技术信息: {msg}"
    )


def _ocr_upstream_network_hint() -> str:
    return (
        "若测试站与 OCR 在同一台机器上，请将「OCR 服务地址」设为 http://127.0.0.1:8000，"
        "不要填本机局域网 IP（否则可能连接失败或超时）。"
    )


async def _require_ocr_service(ocr_base: str) -> None:
    """调用 OCR 接口前先探测 /health；未启动则返回 503 与明确中文说明。"""
    base = (ocr_base or DEFAULT_OCR_BASE).rstrip("/")
    url = f"{base}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
    except httpx.RequestError as exc:
        # 含 ConnectError、网络不可达、DNS 等（不同版本 httpx/httpcore 异常类型不一）
        raise HTTPException(
            status_code=503,
            detail=(
                "OCR 微服务未启动或不可达：无法连接到 "
                f"{url}。请先在项目根目录执行启动脚本（如 startupv5s.bat），或使用 "
                "`python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` "
                f"后再试。技术信息: {exc!s}"
            ),
        ) from exc
    except (ConnectionError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OCR 微服务未启动或网络异常：{exc!s}。请确认 {base} 上 OCR 进程已监听。",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"检查 OCR 微服务时出错（{url}）：{exc!s}",
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


def _json_path_for(img_path: Path) -> Path:
    return img_path.with_suffix(".json")


def _image_creation_time(p: Path) -> float:
    """图片文件「创建时间」用于列表倒序（新在前）。

    Windows：`st_ctime` 为创建时间。
    Linux/macOS：优先 `st_birthtime`（若有），否则退回 `st_mtime`。
    """
    st = p.stat()
    if sys.platform == "win32":
        return float(st.st_ctime)
    return float(getattr(st, "st_birthtime", st.st_mtime))


def _image_files(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    # 按图片创建时间倒序；同名 secondary 保证稳定
    files.sort(key=lambda p: (-_image_creation_time(p), p.name.lower()))
    return files


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


def _ocr_upstream_error_detail(resp: httpx.Response) -> str:
    """解析 OCR 微服务返回的 JSON（FastAPI detail）或原文，供测试页展示真实原因。"""
    code = resp.status_code
    text = (resp.text or "").strip()
    if not text:
        return f"OCR 返回 HTTP {code}（无响应体）"
    try:
        data = resp.json()
        if isinstance(data, dict):
            d = data.get("detail")
            if isinstance(d, str):
                return f"OCR 返回 HTTP {code}: {d}"
            if isinstance(d, list):
                parts = []
                for item in d:
                    if isinstance(item, dict) and item.get("msg") is not None:
                        parts.append(str(item["msg"]))
                    else:
                        parts.append(str(item))
                return f"OCR 返回 HTTP {code}: " + "; ".join(parts)
            if data.get("message") is not None:
                return f"OCR 返回 HTTP {code}: {data['message']}"
    except Exception:
        pass
    snippet = text[:2000]
    return f"OCR 返回 HTTP {code}: {snippet}"


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
    """画布手写签名：保存为 test/data/HandWrite/{纳秒tick}.png，调用 /v1/ocr/general，写回同名 .json。"""
    ocr_base = (ocrBase or DEFAULT_OCR_BASE).rstrip("/")
    content = await file.read()
    await _require_ocr_service(ocr_base)

    folder = DATA_DIR / "HandWrite"
    folder.mkdir(parents=True, exist_ok=True)
    tick = time.time_ns()
    stem = f"{tick:019d}"
    img_path = folder / f"{stem}.png"
    img_path.write_bytes(content)

    target = f"{ocr_base}/v1/ocr/general"
    files = {"file": (img_path.name, content, file.content_type or "image/png")}
    retries = max(0, int(os.getenv("OCR_POST_RETRIES", "2")))
    retry_delay = float(os.getenv("OCR_POST_RETRY_DELAY_SEC", "2"))
    resp: httpx.Response | None = None
    try:
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=_ocr_upstream_timeout()) as client:
                    resp = await client.post(target, files=files)
                break
            except (httpx.ReadError, httpx.RemoteProtocolError) as exc:
                if attempt < retries:
                    log.warning(
                        "handwriting POST %s ReadError/RemoteProtocol (attempt %s/%s): %s; retry in %ss",
                        target,
                        attempt + 1,
                        retries + 1,
                        exc,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                log.warning("handwriting POST %s failed: %s", target, exc, exc_info=True)
                raise HTTPException(
                    status_code=502,
                    detail=_ocr_request_error_detail(exc, target),
                ) from exc
            except httpx.RequestError as exc:
                log.warning("handwriting POST %s failed: %s", target, exc, exc_info=True)
                raise HTTPException(
                    status_code=502,
                    detail=_ocr_request_error_detail(exc, target),
                ) from exc
    except HTTPException:
        raise
    except (ConnectionError, OSError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"调用 OCR 识别接口时网络异常：{exc!s}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"调用 OCR 识别接口异常：{exc!s}",
        ) from exc

    if resp is None:
        raise HTTPException(status_code=502, detail="OCR 未返回响应（内部错误）")

    if resp.status_code >= 400:
        log.warning(
            "handwriting OCR HTTP %s: %s",
            resp.status_code,
            (resp.text or "")[:2000],
        )
        raise HTTPException(status_code=502, detail=_ocr_upstream_error_detail(resp))

    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"invalid ocr json: {exc}") from exc

    jp = img_path.with_suffix(".json")
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "tick": stem,
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
        async with httpx.AsyncClient(timeout=_ocr_upstream_timeout()) as client:
            resp = await client.post(target, files=files)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=_ocr_upstream_error_detail(resp))
            return resp.json()
    except HTTPException:
        raise
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "调用 OCR 识别接口时网络失败或超时（此前 /health 已通过）。"
                f"{_ocr_upstream_network_hint()} "
                f"目标: {target}。技术信息: {exc!s}"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"调用 OCR 识别接口异常：{exc!s}") from exc


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
    async with httpx.AsyncClient(timeout=_ocr_upstream_timeout()) as client:
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

