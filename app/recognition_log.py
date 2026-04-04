"""按识别类型、按日写入 app/logs/<类型>_YYYY-MM-DD.log，仅记录成功结果与错误。"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

# 与路由对应的日志分类（文件名片段）
KIND_HANDWRITING = "handwriting"
KIND_IDCARD = "idcard"
KIND_VEHICLE_LICENSE = "vehicle_license"
KIND_DRIVER_LICENSE = "driver_license"


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _log_path(kind: str) -> Path:
    return LOG_DIR / f"{kind}_{_today_str()}.log"


def _append_line(kind: str, line: str) -> None:
    path = _log_path(kind)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
            if not line.endswith("\n"):
                f.write("\n")


def _json_compact(obj: Any, max_len: int = 12000) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) > max_len:
        return s[: max_len - 20] + "...(truncated)"
    return s


def log_success(kind: str, trace_id: str, elapsed_ms: int, summary: dict[str, Any]) -> None:
    """记录一次成功识别：含 docType、text、fields 等摘要。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "traceId": trace_id,
        "elapsedMs": elapsed_ms,
        **summary,
    }
    line = f"{ts} [OK] {_json_compact(payload)}"
    _append_line(kind, line)


def log_error(
    kind: str,
    trace_id: str,
    elapsed_ms: int,
    *,
    category: str,
    message: str,
    traceback_text: str | None = None,
) -> None:
    """记录错误：category 如 exception / client_error。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"{ts} [ERROR] category={category} traceId={trace_id} elapsedMs={elapsed_ms}",
        f"message={message}",
    ]
    if traceback_text:
        parts.append("traceback:\n" + traceback_text.rstrip())
    _append_line(kind, "\n".join(parts) + "\n")
