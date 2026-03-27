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

## 重要提醒
- Windows 下服务启动以 `startup.bat` 为准
- 不要破坏现有 API 返回协议与字段兜底策略
