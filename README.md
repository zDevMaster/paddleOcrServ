# 内网 Python OCR 微服务（FastAPI）

**相关文档**

- **[服务器部署.md](服务器部署.md)**：内网 Windows 服务器拷贝清单、离线安装、`startup.bat` 启动、任务计划开机自启  
- **[CSharp-IIS-调用示例.md](CSharp-IIS-调用示例.md)**：IIS 场景下 C# 调用示例（JSON base64 等）

面向 IIS 下 C# 多线程 HTTP 调用的 OCR 服务模板，目标：
- 稳定并发：每个 worker 进程只加载一份模型，靠多进程扩展
- 可回溯：保留原始 OCR 行结果（文本、框、分数）
- 结构化字段必出：字段兜底 + 正则校验 + 缺失清单

## 1. 技术栈
- FastAPI（HTTP/JSON）
- PaddleOCR（中文 OCR）
- 并发承载：**Linux** 可用 Gunicorn + UvicornWorker；**Windows** 请用项目根目录 `startup.bat`（内部为 uvicorn 多进程）
- OpenCV（图像预处理 + 质量评分）

## 2. 接口

### `GET /health`
健康检查。

### `POST /v1/ocr/general`
通用 OCR（手写/印刷都可），返回原始行结果 + 全文/行文本/平均置信度。

### `POST /v1/ocr/document/{doc_type}`
证件 OCR（结构化字段 + 原始 OCR + 校验 + 质量）  
`doc_type` 支持：
- `idcard`
- `driver_license`
- `vehicle_license`
- `handwriting`（可选）

## 3. 请求方式

### A. multipart/form-data（推荐）
- 字段：`file`（图片文件）

### B. JSON + base64
```json
{
  "imageBase64": "....",
  "docType": "idcard",
  "options": {
    "maxEdge": 1600
  }
}
```

## 4. 统一返回结构
```json
{
  "success": true,
  "traceId": "uuid",
  "elapsedMs": 123,
  "data": {
    "docType": "idcard",
    "fields": {
      "姓名": { "value": "张三", "confidence": 0.88, "source": "anchor:姓名" }
    },
    "text": "姓名 张三\n..."
  }
}
```

## 5. 与 C# DTO 对齐建议
- `fields` 中字段名使用中文键（如 `身份证号`、`准驾车型`、`车牌号`），可直接映射你的业务类。
- 若字段未识别，仍会输出该键：`value=""`、`source="fallback_missing"`（不再单独返回 `missingFields`）。
- 日期字段统一为 `yyyy-MM-dd` 字符串，C# 端可按 `DateTime?` 解析。

## 6. 本地运行

**Windows（推荐）**  
安装依赖后，在项目根目录执行 **`startup.bat`**，或与脚本等价的手动命令：

```powershell
cd E:\paddleOcr
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

**Linux（可多进程生产）**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m gunicorn -c gunicorn_conf.py app.main:app
```

> 说明：`run.ps1` 依赖的参数名可能与 PowerShell 内置变量冲突；Windows 日常请以 **`startup.bat`** 为准。详见 [服务器部署.md](服务器部署.md)。

## 7. IIS 部署（内网）
常见方式是 IIS 反向代理到本服务（例如 `http://127.0.0.1:8000`）：
- IIS：站点启用 ARR + URL Rewrite
- `/health` 用于探活
- C# 客户端统一反序列化顶层 DTO（`success/traceId/elapsedMs/data`）
- 调用示例见 [CSharp-IIS-调用示例.md](CSharp-IIS-调用示例.md)

## 8. 并发与稳定建议
- 单请求内部保持串行，避免在请求内并发 OCR。
- 按 CPU 核数调整 `OCR_WORKERS`（默认 `cpu_count/2`）。
- 生产建议加请求日志（带 `traceId`）与图片留档策略（按合规要求存储）。

## 9. 内网离线部署准备（外网机器先打包）
内网环境无法联网时，建议在外网机器提前准备 4 类资产，再整体拷贝到内网服务器：
- 运行时：Python 安装包（建议 3.10.x 或 3.11.x，64 位）
- 依赖包：项目依赖对应的离线 `wheel` 包
- Paddle 推理库：`paddlepaddle`（CPU）对应版本 wheel
- PaddleOCR 模型文件：检测/识别/方向分类模型目录

本项目已内置离线目录：`offline_bundle`，测试通过后可直接整体复制到服务器。

推荐离线包目录结构（项目内已创建）：
```text
offline_bundle/
  python/
    python-3.10.x-amd64.exe
  wheels/
    requirements-lock.txt
    *.whl
  paddle/
    paddlepaddle-*.whl            # CPU
  models/
    ch_PP-OCRv4_det_infer/
    ch_PP-OCRv4_rec_infer/
    ch_ppocr_mobile_v2.0_cls_infer/
  project/
    paddleOcr/                    # 当前项目代码
```

## 10. 外网机器准备步骤（可联网）

### 10.0 一键准备（推荐）
项目内已提供脚本：
- `scripts/prepare_offline_assets.ps1`
- `scripts/download_models.py`

在外网机器执行：
```powershell
cd E:\paddleOcr
.\scripts\prepare_offline_assets.ps1 -PythonExe python -PaddleVersion 3.3.1
```

执行后会把依赖 wheel、Paddle CPU wheel、PaddleOCR 模型下载到 `offline_bundle` 对应目录。

### 10.1 固定 Python 与依赖版本
建议先生成锁定文件，避免内网安装时版本漂移：
```powershell
pip freeze > requirements-lock.txt
```

### 10.2 下载离线 wheel（含传递依赖）
在外网机器执行：
```powershell
mkdir wheels
pip download -r requirements.txt -d wheels
pip download -r requirements-lock.txt -d wheels
```

### 10.3 下载 Paddle 推理库（仅 CPU）
- 下载 `paddlepaddle` 对应 Python 版本 wheel

示例（仅示意，版本以 Paddle 官网兼容矩阵为准）：
```powershell
pip download paddlepaddle==<cpu_version> -d paddle
```

### 10.4 准备 PaddleOCR 模型文件
需提前下载并放入内网可访问目录（例如 `E:\ocr-models\`），至少包括：
- 文本检测模型（det）
- 文本识别模型（rec）
- 方向分类模型（cls）

建议按固定目录存放，后续在服务启动参数或环境变量中指定模型路径。

## 11. 内网服务器需要安装的内容（清单）

### 11.1 必装项
- Windows x64（Windows Server 2016 / Windows 10 / Windows 11）
- Python 运行时（与外网 wheel 对应版本）
- VC++ 运行库（若部分二进制包要求）
- 项目代码（本仓库）
- 离线 wheels 目录
- Paddle 推理库 wheel（CPU）
- PaddleOCR 模型目录（det/rec/cls）

## 12. 内网服务器安装步骤（离线）

**完整步骤（拷贝清单、版本对照、任务计划自启）见 [服务器部署.md](服务器部署.md)。**

建议直接复制整个项目目录（包含 `offline_bundle`）到内网服务器。  
以下示例假设项目路径为 `E:\paddleOcr`：

1) 安装 Python（版本需与 `offline_bundle\wheels` 中 wheel 的 `cp3xx` 一致）  
2) 创建虚拟环境并激活  
3) 先安装 Paddle（CPU），再安装锁定依赖  
4) 模型目录使用项目内相对路径（默认无需改）  
5) 运行 **`startup.bat`** 启动服务并访问 `/health`

示例命令：
```powershell
cd E:\paddleOcr
python -m venv .venv
.venv\Scripts\activate

# 先安装 Paddle（CPU，版本与 offline_bundle\paddle 中文件一致）
pip install --no-index --find-links .\offline_bundle\paddle paddlepaddle==3.3.1

# 再安装项目依赖（与干净环境锁定一致）
pip install --no-index --find-links .\offline_bundle\wheels -r .\offline_bundle\wheels\requirements-lock.txt

# 启动（Windows）
.\startup.bat
```

### 12.1 程序中的模型相对路径（默认）
程序默认读取以下相对路径（位于项目根目录）：
- `offline_bundle/models/ch_PP-OCRv4_det_infer`
- `offline_bundle/models/ch_PP-OCRv4_rec_infer`
- `offline_bundle/models/ch_ppocr_mobile_v2.0_cls_infer`

如需覆盖，可设置环境变量：
- `OCR_DET_MODEL_DIR`
- `OCR_REC_MODEL_DIR`
- `OCR_CLS_MODEL_DIR`

## 13. 启动服务指令（Windows）

项目根目录执行 **`startup.bat`**（已内置 uvicorn 多进程、`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` 等内网友好默认值）。

可选环境变量（在运行前于同一 cmd 窗口 `set`）：

```bat
set OCR_WORKERS=4
set OCR_PORT=8000
set OCR_HOST=0.0.0.0
```

详细说明见 [服务器部署.md](服务器部署.md) 第 4 节。

## 14. 配置开机自动启动（Windows Server 2016 / 10 / 11）

使用任务计划程序，在**系统启动时**执行项目根目录的 **`startup.bat`**（程序填 `cmd.exe`，参数 `/c "E:\paddleOcr\startup.bat"`，“起始于”填 `E:\paddleOcr`）。

分步截图级说明与验证方法见 **[服务器部署.md](服务器部署.md) 第 5 节**。

## 15. 离线部署校验建议
- 执行 `GET /health`，确认服务可用
- 用一张身份证/驾驶证/行驶证样例图调用接口，检查：
  - `fields` 是否完整输出（缺失字段应返回 `value=""`）
  - `fields` 每个键是否包含 `value/confidence/source`
- 在 C# 侧做 20~100 并发压测，观察耗时与超时率，再调整 `OCR_WORKERS`

## 16. 生产落地建议（内网）
- 把模型目录放在固定路径（如 `E:\ocr-models`），避免误删
- 固化版本：Python、Paddle、PaddleOCR、模型版本都记录到发布单
- 每次升级先在预发布内网环境回归再切生产

