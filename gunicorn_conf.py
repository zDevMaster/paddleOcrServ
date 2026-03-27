import multiprocessing
import os

# CPU 模式: 通过多进程提升并发吞吐
workers = int(os.getenv("OCR_WORKERS", str(max(1, multiprocessing.cpu_count() // 2))))
worker_class = "uvicorn.workers.UvicornWorker"
bind = os.getenv("OCR_BIND", "0.0.0.0:8000")
timeout = int(os.getenv("OCR_TIMEOUT", "120"))
keepalive = 5
max_requests = 1000
max_requests_jitter = 100

