"""最小 FastAPI，用于排查 uvicorn 是否能正常监听。"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}
