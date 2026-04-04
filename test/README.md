# test 目录说明

## 目录用途

- `data/`：测试图片与数据目录（已在 `test/.gitignore` 中忽略，不入库）
- `test_site.py`：测试网站后端（批量识别、分页结果、静态图片读取）
- `site/index.html`：测试入口页
- `site/batch_idcard.html`：身份证批量测试页
- `site/batch_vehicle_license.html`：行驶证批量测试页
- `site/batch_driver_license.html`：驾驶证批量测试页
- `site/batch_handwriting.html`：手写签名画布 → 保存 `HandWrite/{guid}.png` + 识别 `json`
- `start_test_site.bat`：本地启动测试网站脚本

## 启动测试网站

先确保 OCR 微服务已启动（默认 `http://127.0.0.1:8000`），然后执行：

```bat
cd /d E:\paddleOcr\test
start_test_site.bat
```

浏览器打开：

- `http://127.0.0.1:9000`
- 进入对应批量页面：
  - 身份证：`/batch/idcard`
  - 行驶证：`/batch/vehicle_license`
  - 驾驶证：`/batch/driver_license`
  - 手写签名：`/batch/handwriting`（网页/触屏书写，提交后以 GUID 存图并识别）

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

