"""供 uvicorn dictConfig 使用：在打开日志文件前创建父目录（避免从子目录启动时 FileNotFoundError）。"""
from __future__ import annotations

import logging
from pathlib import Path


class EnsureDirFileHandler(logging.FileHandler):
    def __init__(
        self,
        filename: str,
        mode: str = "a",
        encoding: str | None = "utf-8",
        delay: bool = False,
        errors: str | None = None,
    ) -> None:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, mode, encoding=encoding, delay=delay, errors=errors)
