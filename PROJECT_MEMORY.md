# 项目记忆（Project Memory）

> 用于跨机器/新会话快速恢复上下文。更新本文件时请保持精简且准确。

## 1. 项目目标
- 内网部署 OCR 微服务（FastAPI + PaddleOCR）。
- 提供证件识别与通用识别接口，面向 IIS 下 C# HTTP 调用。

## 2. 已定接口
- `GET /health`
- `POST /v1/ocr/general`
- `POST /v1/ocr/document/{doc_type}`：`idcard` / `vehicle_license` / `driver_license`

## 3. 返回协议（当前）
- 顶层：`success`、`traceId`、`elapsedMs`
- `data`：`docType`、`fields`、`text`
- 不返回：`raw`、`validation`、`quality`、`missingFields`
- 缺失字段必须在 `fields` 中返回，`value=""`

## 4. 部署关键点
- Windows 启动使用 `startup.bat`（内部 `uvicorn` 多进程）。
- `gunicorn` 不作为 Windows 运行方式。
- 离线部署依赖目录：`offline_bundle/paddle`、`offline_bundle/wheels`、`offline_bundle/models`
- 文档：`服务器部署.md`

## 5. C# 对接文档
- 文件：`CSharp-IIS-调用示例.md`
- 当前示例以 JSON + base64 为主，并包含 base64 工具方法。

## 6. 测试网站
- 目录：`test/`
- 批量测试页：
  - `/batch/idcard`
  - `/batch/vehicle_license`
  - `/batch/driver_license`
- 每次批量可选：`5/10/20/50/100`
- 仅处理未生成同名 `.json` 的图片，支持断点续跑。
- `test/data` 已忽略，不入库。

## 7. 协作约定
- 每次完成变更后执行 git commit。
- git push 由用户手动控制。
