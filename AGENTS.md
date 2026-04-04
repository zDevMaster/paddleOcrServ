# AGENTS 使用指引

本仓库用于保存对 AI 代理的持久约束与项目上下文。

## 必读文件
1. `.cursor/rules/project-core.mdc`
2. `.cursor/rules/python-fastapi.mdc`（处理 Python 文件时）
3. `PROJECT_MEMORY.md`

## 工作规则
- 输出语言：简体中文
- 完成用户请求的改动后，执行 git commit
- 除非用户明确要求，不执行 git push
- **修改 `app/` 下 OCR 微服务相关代码后，应在同一会话内自行重启微服务**（结束占用 `8000` 端口的进程后，在项目根用 `.venv` 执行 `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`，或与根目录 `startupV4m.bat` / `startupv5m.bat` / `startupv5s.bat` 等价；脚本默认监听 `0.0.0.0`），使用户无需手动重启即可验证。

## 重要提醒
- Windows 下服务启动以根目录 `startupV4m.bat` / `startupv5m.bat` / `startupv5s.bat` 为准（见 README / 服务器部署.md）
- 不要破坏现有 API 返回协议与字段兜底策略
