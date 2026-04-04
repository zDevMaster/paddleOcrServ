# 项目记忆（Project Memory）

> 用于跨机器/新会话快速恢复上下文。更新本文件时保持“关键结论优先、可执行优先”。

## 1. 项目定位
- 项目目标：在内网部署 Python OCR 微服务，供 IIS 下 C# 多线程 HTTP 调用。
- 场景覆盖：身份证、行驶证、驾驶证、手写识别；同时支持人工测试与批量回归。

## 2. 当前 API 契约（不可随意破坏）
- `GET /health`
- `POST /v1/ocr/general`
- `POST /v1/ocr/document/{doc_type}`：`idcard` / `vehicle_license` / `driver_license` / `handwriting`

返回结构（已定版）：
- 顶层：`success`、`traceId`、`elapsedMs`
- `data`：`docType`、`fields`、`text`
- 已移除：`raw`、`validation`、`quality`、`missingFields`
- 规则：结构化字段必须输出；缺失字段也要有键，且 `value=""`

## 3. OCR 与抽取策略要点
- 每个进程内 OCR 模型单例（避免重复加载）。
- 证件抽取以“关键词锚点 + 正则”组合实现，字段缺失走 `fallback_missing`。
- 默认模型路径使用相对目录：
  - `offline_bundle/models/ch_PP-OCRv4_det_infer`
  - `offline_bundle/models/ch_PP-OCRv4_rec_infer`
  - `offline_bundle/models/ch_ppocr_mobile_v2.0_cls_infer`

## 4. 部署运行结论（本次会话已验证）
- Windows 上不要用 `gunicorn` 运行（依赖 `fcntl`，不可用）。
- Windows 推荐统一用 `startup.bat`（内部 `uvicorn` 多进程）。
- `run.ps1` 历史上有 `Host` 参数与 PowerShell 内置变量冲突风险，不作为主入口。
- 内网环境建议设置 `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=1`，避免联网检查卡顿。

## 5. 离线交付目录（当前仓库已具备）
- `offline_bundle/paddle/`：Paddle CPU 及依赖 wheel
- `offline_bundle/wheels/`：项目依赖离线 wheel（含 `requirements-lock.txt`）
- `offline_bundle/models/`：OCR 模型
- `安装程序/`：Python/VC++ 安装程序

版本一致性关键点：
- Python 主版本必须匹配 wheel 标签（如 `cp313`）。
- 离线安装优先用 `offline_bundle/wheels/requirements-lock.txt` 保证可复现；清单已包含 `paddlepaddle==3.3.1` 及其传递依赖，与根目录 `requirements.txt` 一致。
- 外网打包：`scripts/prepare_offline_assets.ps1` 按锁定清单下载 wheels，并额外把 Paddle CPU 栈下载到 `offline_bundle/paddle/`（兼容「两步安装」）；收尾执行 `scripts/verify_offline_bundle.py` 校验模型与离线 pip。

## 6. 文档地图（按用途）
- `README.md`：总览与快速入口
- `服务器部署.md`：内网拷贝清单、环境、`offline_bundle` 完整性（第 3 节）、离线 pip（第 4 节）、启动、任务计划（第 6 节）、常见问题
- `CSharp-IIS-调用示例.md`：C# DTO 映射与 base64 调用示例
- `test/README.md`：测试网站与批量测试说明

## 7. 测试网站（test）能力
- 入口：`test/start_test_site.bat`，默认 `http://127.0.0.1:9000`
- 批量页面：
  - `/batch/idcard`
  - `/batch/vehicle_license`
  - `/batch/driver_license`
- 批量规则：
  - 每次处理批次可选：`5/10/20/50/100`
  - 仅处理尚未生成同名 `.json` 的图片（断点续跑）
  - 结果页显示全部图片（含未识别），并支持分页核对
- 数据目录：`test/data`（已在 `test/.gitignore` 忽略，不入库）

## 8. 协作约定（用户明确要求）
- 语言：始终使用简体中文。
- 每次完成改动后自动 `git commit`。
- `git push` 由用户手动控制，助手不主动 push。
