# test 目录说明

## 目录用途

- `data/`：测试图片与数据目录（已在 `test/.gitignore` 中忽略，不入库）
- `test_site.py`：测试网站后端（批量识别、分页结果、静态图片读取）
- `site/index.html`：测试入口页
- `site/batch_idcard.html`：身份证批量测试页
- `site/batch_vehicle_license.html`：行驶证批量测试页
- `site/batch_driver_license.html`：驾驶证批量测试页
- `site/batch_handwriting.html`：手写签名画布 → 保存 `HandWrite/{纳秒tick}.png` + 识别 `json`
- `start_test_site.bat`：启动测试网站（默认监听 `0.0.0.0:9000`，本机与局域网均可访问；仅本机可设 `TEST_SITE_HOST=127.0.0.1`；终端日志使用项目根目录 `uvicorn_log_config.json` 带**时间戳**）
- 测试站**转发 OCR 微服务**时使用 **`application/json` + `imageBase64`**（与 C# 示例、`ImageJsonRequest` 一致）；浏览器到测试站仍可为表单/文件上传，由服务端读字节后编码
- 测试站调用 OCR 的 HTTP 超时默认 **600s**（首请求会加载模型）；若仍超时可在运行测试站前设置环境变量 `OCR_UPSTREAM_TIMEOUT=1200`
- 若出现 `ReadError`（对端关闭连接），手写提交会自动重试，次数由 **`OCR_POST_RETRIES`**（默认 `2`，即最多 3 次请求）、间隔 **`OCR_POST_RETRY_DELAY_SEC`**（默认 `2` 秒）控制

## 启动测试网站

先确保 OCR 微服务已启动（默认 `http://127.0.0.1:8000`），然后执行：

```bat
cd /d E:\paddleOcr\test
start_test_site.bat
```

浏览器打开：

- 本机：`http://127.0.0.1:9000`
- 同网其它电脑：`http://<本机局域网IP>:9000`（若不通：确认用 `start_test_site.bat` 默认 host、并在 Windows 防火墙中放行 **入站** TCP **9000**）
- 进入对应批量页面：
  - 身份证：`/batch/idcard`
  - 行驶证：`/batch/vehicle_license`
  - 驾驶证：`/batch/driver_license`
  - 手写签名：`/batch/handwriting`（网页/触屏书写，提交后以时间戳 tick 存图并识别）

## 批量测试规则

- 每次批量处理仅处理 **未生成同名 `.json`** 的图片
- 每次批量数量可选，范围 **5-100**
- 识别结果保存为同名 `.json`（示例：`a.jpg` -> `a.json`）
- 下次点击“批量测试”会自动继续处理剩余未识别文件

## 结果浏览

- 展示该目录下**全部图片**（包含已识别与未识别）
- 左侧显示原始图片，右侧显示对应 `.json` 内容
- 通过分页加载便于人工核对

## data 目录建议结构

- `test/data/idcard`
- `test/data/VehicleLicense`
- `test/data/DrivingLicense`

