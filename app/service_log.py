"""旧版：运行时向 uvicorn logger 挂载文件 Handler。已改为在 uvicorn_log_config.json 中用 FileHandler 写 app/logs/，勿在应用 import 阶段调用 install_uvicorn_file_mirror。"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import TextIO

from uvicorn.logging import AccessFormatter, DefaultFormatter

LOG_DIR = Path(__file__).resolve().parent / "logs"

_stream_lock = threading.Lock()
_streams: dict[tuple[str, str, str], TextIO] = {}

_installed = False


def _get_append_stream(log_dir: Path, suffix: str, day: str) -> TextIO:
    key = (str(log_dir.resolve()), suffix, day)
    with _stream_lock:
        if key not in _streams:
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"{day}_{suffix}.log"
            f: TextIO = open(path, "a", encoding="utf-8")
            _streams[key] = f
        return _streams[key]


class DailySuffixFileHandler(logging.Handler):
    """写入 ``{date}_{suffix}.log``；格式由 setFormatter 决定。"""

    def __init__(self, log_dir: Path, suffix: str) -> None:
        super().__init__()
        self.log_dir = log_dir
        self.suffix = suffix

    def emit(self, record: logging.LogRecord) -> None:
        try:
            day = datetime.now().strftime("%Y-%m-%d")
            msg = self.format(record)
            with _stream_lock:
                stream = _get_append_stream(self.log_dir, self.suffix, day)
                stream.write(msg + "\n")
                stream.flush()
        except Exception:
            self.handleError(record)


def install_uvicorn_file_mirror() -> None:
    """把与终端一致的 uvicorn 日志写入 ``{date}_base.log``。幂等。

    - 默认/错误类日志：只挂在 ``uvicorn`` 上，子 logger ``uvicorn.error`` 会向上传播，避免重复写。
    - 访问日志：挂在 ``uvicorn.access``（propagate=False）。
    """
    global _installed
    if _installed:
        return

    datefmt = "%Y-%m-%d %H:%M:%S"
    fmt_default = DefaultFormatter(
        fmt="%(asctime)s | %(levelprefix)s %(message)s",
        datefmt=datefmt,
        use_colors=False,
    )
    fmt_access = AccessFormatter(
        fmt='%(asctime)s | %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        datefmt=datefmt,
        use_colors=False,
    )

    def _has_mirror(lg: logging.Logger) -> bool:
        return any(isinstance(h, DailySuffixFileHandler) for h in lg.handlers)

    h_def = DailySuffixFileHandler(LOG_DIR, "base")
    h_def.setFormatter(fmt_default)
    h_def.setLevel(logging.INFO)

    h_acc = DailySuffixFileHandler(LOG_DIR, "base")
    h_acc.setFormatter(fmt_access)
    h_acc.setLevel(logging.INFO)

    lg_uv = logging.getLogger("uvicorn")
    if not _has_mirror(lg_uv):
        lg_uv.addHandler(h_def)

    lg_uva = logging.getLogger("uvicorn.access")
    if not _has_mirror(lg_uva):
        lg_uva.addHandler(h_acc)

    _installed = True
